# -*- coding: utf-8 -*-

import click
import filecmp
import os
import pandas as pd
import pathlib
import sqlite3
import sys
from azure.storage.blob import BlobServiceClient
from datetime import datetime
from os.path import expanduser
from pathlib import Path
from shutil import copy2


class BackupContext(object):
    def __init__(self, connection_string, blob_container_name, year, month, device):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.dbcursor = self.db.cursor()
        self.connection_string = connection_string
        self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        self.blob_container_name = blob_container_name
        # Get a client to interact with the container
        self.container_client = self.blob_service_client.get_container_client(self.blob_container_name)
        self.homedir = expanduser("~")
        self.year = year
        self.month = month
        self.device = device
        self.dir_prefix = "photos/{year}/{month}/{device}/".format(
            year=self.year, month=self.month, device=self.device
        )
        self.dropbox_camera_uploads_dir = pathlib.Path(
            "{0}/Dropbox/Camera Uploads/".format(self.homedir)
        )
        self.local_blob_dir = pathlib.Path(
            "{homedir}/Pictures/blob/{blob}/".format(
                homedir=self.homedir, blob=self.blob_container_name
            )
        )
        self.local_working_dir = pathlib.Path(
            "{local_blob_dir}/{dir_prefix}".format(
                local_blob_dir=self.local_blob_dir, dir_prefix=self.dir_prefix
            )
        )
        # The file extensions that we'll operate on
        self.supported_file_extensions = ["jpg", "png", "mov", "3gp", "heic", "mp4"]
        self.video_file_extensions = [".mov", ".3gp", ".mp4"]

        self.init_db()

    def get_glob_pattern(self, file_ext):
        if self.device == "NikonCoolpix":
            pattern = "**/*DSCN*.{}".format(file_ext.upper())
        else:
            pattern = "**/{}-{}-*.{}".format(self.year, self.month, file_ext)
        return pattern

    def init_db(self):
        # Walk Dropbox and working dir paths and find all files matching
        # the given year/month.
        # TODO - if we're asked to 'lsdropbox' then there's no need to glob
        # other dir contents.
        self.dropbox_filenames = []
        self.working_dir_filenames = []
        for file_ext in self.supported_file_extensions:
            pattern = self.get_glob_pattern(file_ext)
            dropbox_glob = self.dropbox_camera_uploads_dir.glob(pattern)
            self.dropbox_filenames.extend([x.name for x in sorted(dropbox_glob)])
            workdir_glob = self.local_working_dir.glob(pattern)
            self.working_dir_filenames.extend([x.name for x in sorted(workdir_glob)])
        # Get bucket contents for year/month/device
        #self.bucket_file_paths = [
        #    obj.key
        #    for obj in self.bucket.objects.filter(Prefix=self.dir_prefix)
        #    if Path(obj.key).suffix != ""
        #]
        #self.bucket_filenames = [Path(x).name for x in self.bucket_file_paths]
        self.blob_container_paths = [
            blob.name
            for blob in self.container_client.list_blobs()
            if Path(blob.name).suffix != ""
        ]
        self.blob_container_filenames = [Path(x).name for x in self.blob_container_paths]

        #    if Path(x).suffix is not '']
        #    x.split("/")[-1] for x in self.bucket_file_paths]

        # Populate DB
        # TODO - add an IsVideo column so we don't have to check for .mov extension
        # TODO
        # Use dataset instead of raw queries:
        # https://dataset.readthedocs.io/en/latest/
        self.dbcursor.execute(
            """DROP TABLE IF EXISTS files"""
        )
        self.dbcursor.execute(
            """CREATE TABLE files (
            Filename TEXT PRIMARY KEY,
            InDropbox INTEGER DEFAULT 0,
            InWorkingDir INTEGER DEFAULT 0,
            InBlob INTEGER DEFAULT 0)"""
        )
        for file_name in self.dropbox_filenames:
            self.do_upsert_true_value_for_column(
                file_name=file_name, column="InDropbox"
            )
        for file_name in self.working_dir_filenames:
            self.do_upsert_true_value_for_column(
                file_name=file_name, column="InWorkingDir"
            )
        for file_name in self.blob_container_filenames:
            self.do_upsert_true_value_for_column(file_name=file_name, column="InBlob")

    def do_upsert_true_value_for_column(self, file_name, column):
        #print("Inserting '{}' into column '{}'".format(file_name, column))
        self.dbcursor.execute(
            """
            INSERT INTO files (Filename, {column})
            VALUES ('{file_name}', 1)
            ON CONFLICT (Filename)
            DO UPDATE SET {column} = 1 WHERE Filename = '{file_name}'""".format(
                file_name=file_name, column=column
            )
        )
        # self.dbcursor.execute("""
        #    INSERT INTO files (Filename, :column)
        #    VALUES (:file_name, 1)
        #    ON CONFLICT (Filename)
        #    DO UPDATE SET :column=1 WHERE Filename=:file_name""", {"column": column, "file_name": file_name})
        self.db.commit()

    def do_upsert_true_value_for_in_blob_column(self, file_name, column):
        #print("Inserting '{}' into column '{}'".format(file_name, column))
        self.dbcursor.execute(
            """
            INSERT INTO files (Filename, InBlob)
            VALUES (:file_name, 1)
            ON CONFLICT (Filename)
            DO UPDATE SET InBlob=1 WHERE Filename=:file_name""",
            {"file_name": file_name},
        )
        self.db.commit()

    def get_file_db_row(self, file_name):
        query = "SELECT * FROM files WHERE Filename = ?"
        row = self.dbcursor.execute(query, (file_name,)).fetchone()
        return row

    def mkdir(self):
        if not os.path.exists(self.local_working_dir):
            click.echo(
                "About to create working dir at {}".format(self.local_working_dir)
            )
            click.confirm("Do you want to continue?", abort=True)
            # Append /video to working dir path since videos are stored separately
            os.makedirs(self.local_working_dir / "video")
        else:
            click.echo(
                "Working dir already exists at {}".format(self.local_working_dir)
            )

    def __repr__(self):
        return "<BackupContext %r>" % self.local_working_dir


pass_backup_context = click.make_pass_decorator(BackupContext)


@click.group()
@click.option(
    "--connection-string", prompt="Connection string", help="The storage account connection string."
)
@click.option(
    "--blob-container-name", prompt="Blob container name", help="The blob container name to upload to."
)
@click.option(
    "--year",
    prompt="Photo year",
    default="{:02}".format(datetime.today().year),
    help="The year dir to use in the working dir path (e.g. 2017).",
)
@click.option(
    "--month",
    prompt="Photo month",
    default="{:02}".format(datetime.today().month),
    help="The month dir to use in the working dir path (e.g. 09).",
)
@click.option(
    "--device",
    prompt="Device name",
    default="iPhone14",
    help="The device name to use in the working dir path.",
)
@click.pass_context
def cli(ctx, connection_string, blob_container_name, year, month, device):
    """
    This utility copies image/video files from ~/Dropbox/Camera Uploads/
    into a local working dir, then uploads the files to a blob container.

    Example usage:\n
      drop2blob workflow\n
      drop2blob diffcontainer\n
      drop2blob rm-dropbox-files
    """
    # Create a BackupContext object and remember it as as the context object.
    # From this point onwards other commands can refer to it by using the
    # @pass_backup_context decorator.
    ctx.obj = BackupContext(connection_string, blob_container_name, year, month, device)


@cli.command()
@pass_backup_context
def mkdir(backup_context):
    """Creates local working dir to copy Dropbox files to.
    will be copied from your Dropbox/Camera Uploads/ dir.
    The working dir files can then be uploaded to a blob container.
    """
    backup_context.mkdir()


@cli.command()
@pass_backup_context
@click.option(
    "--dryrun",
    prompt="Dry run?",
    type=click.BOOL,
    default=True,
    help="Do not actually copy files.",
)
def cp(backup_context, dryrun):
    """Copy files from Dropbox to working dir.

    Note that files with video extensions will be copied into
    a "video" subdir of the working dir.
    """
    # Check for working dir and run mkdir() if it doesn't exist
    backup_context.mkdir()
    click.echo(
        "About to copy files from: {}".format(backup_context.dropbox_camera_uploads_dir)
    )
    click.echo("To local working dir: {}".format(backup_context.local_working_dir))
    dest_images = backup_context.local_working_dir
    dest_videos = backup_context.local_working_dir / "video"

    for dropbox_file_name in backup_context.dropbox_filenames:
        file_row = backup_context.get_file_db_row(dropbox_file_name)
        if file_row["InWorkingDir"]:
            click.echo(
                "Skipping file '{}'; it already exists in workdir".format(
                    dropbox_file_name
                )
            )
            continue
        # Set destination dir
        file_ext = os.path.splitext(dropbox_file_name)[1]
        if file_ext in backup_context.video_file_extensions:
            dest_root = dest_videos
        else:
            dest_root = dest_images
        if dryrun:
            click.echo(
                "Dry run; would have copied '{}' to workdir".format(dropbox_file_name)
            )
        else:
            click.echo("Copying '{}' to {}".format(dropbox_file_name, dest_root))
            copy2(
                backup_context.dropbox_camera_uploads_dir / dropbox_file_name, dest_root
            )


@cli.command()
@pass_backup_context
@click.option(
    "--dryrun",
    prompt="Dry run?",
    type=click.BOOL,
    default=True,
    help="Do not actually delete files.",
)
def rm_dropbox_files(backup_context, dryrun):
    """Delete backed-up files in your Camera Uploads dir.
    """
    # Double check that all the files to be deleted in Dropbox also exist
    # in the working dir and the blob container:
    click.echo("Checking for Dropbox files in workdir and blob container...")
    for dropbox_file_name in backup_context.dropbox_filenames:
        file_row = backup_context.get_file_db_row(dropbox_file_name)
        in_workdir = file_row["InWorkingDir"]
        in_blob = file_row["InBlob"]
        dropbox_file_abspath = (
            backup_context.dropbox_camera_uploads_dir / dropbox_file_name
        )
        file_ext = os.path.splitext(dropbox_file_name)[1]
        if file_ext in (backup_context.video_file_extensions):
            workdir_file_abspath = (
                backup_context.local_working_dir / "video" / dropbox_file_name
            )
        else:
            workdir_file_abspath = backup_context.local_working_dir / dropbox_file_name
        if in_workdir and in_blob:
            # Before rm'ing, diff the dropbox and workdir files to make sure
            # neither copy is corrupt
            if filecmp.cmp(dropbox_file_abspath, workdir_file_abspath, shallow=False):
                if dryrun:
                    click.echo(
                        "[dry run] would have deleted Dropbox file '{}'".format(
                            dropbox_file_name
                        )
                    )
                    continue
                else:
                    click.echo("Deleting {}...".format(dropbox_file_abspath))
                    os.remove(dropbox_file_abspath)
            else:
                click.echo(
                    "Error: cmp() failed for Dropbox file '{}' and its workdir backup '{}'!".format(
                        dropbox_file_name, workdir_file_abspath
                    )
                )
                click.echo("Aborting clean; please investigate before continuing.")
                sys.exit(1)
        else:
            click.echo(
                "Skipping rm of Dropbox file '{}'; it's not present in both workdir and blob container...".format(
                    dropbox_file_name
                )
            )
            click.echo("Please run the upload command to back the file up in blob storage first.")
            continue


@cli.command()
@pass_backup_context
def difflocal(backup_context):
    """Diff Dropbox and working dir contents.
    """
    fmt = "{:<40}{:<20}"
    print(fmt.format("File name", "Status"))
    query = "SELECT * FROM files ORDER BY Filename"
    for row in backup_context.dbcursor.execute(query):
        filename = row["Filename"]
        in_dropbox = row["InDropbox"]
        in_workdir = row["InWorkingDir"]
        in_s3 = row["InBlob"]
        dropbox_file_abspath = backup_context.dropbox_camera_uploads_dir / filename
        file_ext = os.path.splitext(filename)[1]
        if file_ext in (backup_context.video_file_extensions):
            workdir_file_abspath = backup_context.local_working_dir / "video" / filename
        else:
            workdir_file_abspath = backup_context.local_working_dir / filename
        if in_dropbox == 1 and in_workdir == 1:
            if filecmp.cmp(dropbox_file_abspath, workdir_file_abspath, shallow=False):
                print(fmt.format(filename, "👍 diff OK"))
            else:
                print(fmt.format(filename, "❌ diff NOT OK - files differ!"))
        elif in_dropbox == 1 and in_workdir == 0:
            click.secho(fmt.format(filename, "dropbox only"), bg="red", fg="white")
        # Silencing since this is a little verbose:
        #elif in_dropbox == 0 and in_workdir == 1:
        #    click.secho(fmt.format(filename, "workdir only"))
        elif in_dropbox == 0 and in_workdir == 0 and in_s3 == 1:
            click.secho(fmt.format(filename, "blob storage only"), bg="blue", fg="white")


@cli.command()
@pass_backup_context
def diffblob(backup_context):
    """Diff working dir and blob container contents.
    """
    fmt = "{:<40}{:<20}"
    print(fmt.format("File name", "Status"))
    query = "SELECT * FROM files ORDER BY Filename"
    for row in backup_context.dbcursor.execute(query):
        filename = row["Filename"]
        in_dropbox = row["InDropbox"]
        in_workdir = row["InWorkingDir"]
        in_s3 = row["InBlob"]
        if in_workdir == 1 and in_s3 == 1:
            print(fmt.format(filename, "👍 found in blob ctr & workdir"))
            # TODO - compare blob container file checksum against md5 of local file?
        elif in_workdir == 1 and in_s3 == 0:
            click.secho(fmt.format(filename, "workdir only"), bg="red", fg="white")
        elif in_workdir == 0 and in_s3 == 1:
            click.secho(fmt.format(filename, "blob storage only"))
        elif in_workdir == 0 and in_s3 == 0 and in_dropbox == 1:
            click.secho(fmt.format(filename, "dropbox only"), bg="red", fg="white")


@cli.command()
@pass_backup_context
@click.option(
    "--dryrun",
    prompt="Dry run?",
    type=click.BOOL,
    default=True,
    help="Do not actually upload files.",
)
def upload(backup_context, dryrun):
    """Uploads local working dir files to the given blob container.
    """
    for workdir_filename in backup_context.working_dir_filenames:
        file_row = backup_context.get_file_db_row(workdir_filename)
        if file_row["InBlob"]:
            # A little too noisy to always display:
            #click.echo(
            #    "Skipping file '{}'; it already exists in blob storage".format(workdir_filename)
            #)
            continue

        bucket_dest_images = backup_context.dir_prefix
        bucket_dest_videos = backup_context.dir_prefix + "video/"
        file_ext = os.path.splitext(workdir_filename)[1]
        if file_ext in backup_context.video_file_extensions:
            bucket_root = bucket_dest_videos
            workdir_file_abspath = (
                backup_context.local_working_dir / "video" / workdir_filename
            )
        else:
            bucket_root = bucket_dest_images
            workdir_file_abspath = backup_context.local_working_dir / workdir_filename

        bucket_file_key = bucket_root + workdir_filename
        if dryrun:
            click.echo(
                "Dry run; would have uploaded '{}' to blob container path '{}'".format(
                    workdir_filename, bucket_file_key
                )
            )
            continue
        else:
            click.echo(
                "Uploading '{}' to blob container path '{}'".format(
                    workdir_file_abspath, bucket_file_key
                )
            )
            # Upload the file
            with open(file=workdir_file_abspath, mode="rb") as data:
                # With the default upload_blob() params large video files almost always
                # time out - setting connection_timeout to a high value seems to avoid that:
                # https://stackoverflow.com/a/71000273
                blob_client = backup_context.container_client.upload_blob(name=bucket_file_key, data=data, overwrite=True, connection_timeout=60)


@cli.command()
@pass_backup_context
@click.option(
    "--dryrun",
    prompt="Dry run?",
    type=click.BOOL,
    default=True,
    help="Do not actually download files.",
)
def download(backup_context, dryrun):
    """Download files from blob container to local dir.
    """
    if not dryrun:
        backup_context.mkdir()
    for key in backup_context.blob_container_paths:
        if dryrun:
            click.echo(
                "Dry run; would have downloaded blob storage object '{}' to '{}'".format(
                    key, "{}/{}".format(backup_context.local_blob_dir, key)
                )
            )
            continue
        else:
            click.echo(
                "Downloading blob object '{}' to '{}'".format(
                    key, "{}/{}".format(backup_context.local_blob_dir, key)
                )
            )
            #backup_context.bucket.download_file(
            #     key, "{}/{}".format(backup_context.local_blob_dir, key)
            #)
            blob_client = backup_context.container_client.get_blob_client(blob=key)
            with open("{}/{}".format(backup_context.local_blob_dir, key), "wb") as download_file:
                download_data = blob_client.download_blob()
                download_file.write(download_data.readall())


@cli.command()
@pass_backup_context
def lsblob(backup_context):
    """Print blob container contents for given year/month/device.
    """
    for key in backup_context.blob_container_paths:
        print(key)


@cli.command()
@pass_backup_context
def lsdb(backup_context):
    """Populate and print DB rows for given year/month/device.
    """
    pd.set_option("display.max_rows", 1000)
    print(pd.read_sql_query("SELECT * FROM files", backup_context.db))


@cli.command()
@pass_backup_context
def lsdropbox(backup_context):
    """Print Dropbox contents for given year/month/device.
    """
    for name in backup_context.dropbox_filenames:
        print(name)


@cli.command()
@pass_backup_context
def lsworkdir(backup_context):
    """Print working dir contents for given year/month/device.
    """
    for filename in backup_context.working_dir_filenames:
        print(filename)


@cli.command()
@click.pass_context
@click.option(
    "--dryrun",
    prompt="Dry run?",
    type=click.BOOL,
    default=True,
    help="Print steps rather than execute them.",
)
def workflow(backup_context, dryrun):
    """Runs all commands for a typical backup workflow.
    """
    backup_context.invoke(mkdir)
    backup_context.invoke(difflocal)
    # TODO - bail out if there's nothing in the dropbox folder, since
    # there's nothing else we can do
    click.confirm(
        "About to copy files to workdir - do you want to continue?", abort=True
    )
    backup_context.forward(cp)
    if dryrun:
        print("Skipping blob container preview step since dryrun mode is on...")
        # NOTE: This is skipped when in a dryrun, since no files were moved on
        # disk in earlier steps, so we can't look at the disk or DB to display
        # what we would actually be doing here...
        # IDEA: What if copying or deleting files triggered an update to
        # the DB, so that we could print what the current state would be?
        # And the code paths that actually do modify files could either
        # query the DB to figure out what to do, or a single function could
        # "sync" the disk with the desired layout expressed in the DB state...
    else:
        click.confirm("About to upload files to blob container - do you want to continue?", abort=True)
        # Reinitialize DB with updated paths, since we may have just moved
        # files into the workdir
        backup_context.obj.init_db()
        backup_context.forward(upload)
        click.echo(
            "All done - to delete your files from Dropbox, run the rm-dropbox-files command."
        )

#@cli.command()
#@pass_backup_context
#def test(backup_context):
#    """test and debugging command
#    """
#    for filename in backup_context.working_dir_filenames:
#        print(filename)
