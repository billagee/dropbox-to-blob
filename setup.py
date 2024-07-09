from setuptools import setup

setup(
    name='drop2blob',
    version='0.1',
    py_modules=['drop2blob'],
    include_package_data=True,
    install_requires=[
        'azure-storage-blob',
        'click',
        'pandas',
    ],
    entry_points='''
        [console_scripts]
        drop2blob=drop2blob:cli
    ''',
)
