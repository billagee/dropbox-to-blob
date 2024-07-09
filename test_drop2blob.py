import pytest
from click.testing import CliRunner
from unittest.mock import Mock
from drop2blob import cli

@pytest.fixture
def mock_backup_context():
    mock_context = Mock()
    mock_context.blob_container_paths = ['path1', 'path2', 'path3']
    return mock_context

def test_lsblob(mock_backup_context, monkeypatch):
    runner = CliRunner()
    
    # Monkeypatch the pass_backup_context decorator to use the mock context
    def mock_decorator(f):
        return lambda *args, **kwargs: f(mock_backup_context, *args, **kwargs)
    
    monkeypatch.setattr('drop2blob.pass_backup_context', mock_decorator)
    
    result = runner.invoke(
        cli, [
            # TODO - use azurite here so we can use a "real" connection string?
            '--connection-string', 'fake_connection_string',
            '--blob-container-name', 'fake_container_name',
            '--year', '2024',
            '--month', '05',
            '--device', 'iPhone14',
            'lsblob',
        ]
    )
    
    assert result.exit_code == 0
    assert 'path1' in result.output
    assert 'path2' in result.output
    assert 'path3' in result.output