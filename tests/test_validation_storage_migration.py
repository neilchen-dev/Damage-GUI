from contextlib import closing

from damage_gui.storage.db import SCHEMA_SQL, connect, ensure_schema
from damage_gui.storage.repositories import JobRepository, PredictionResultRepository


def test_validation_kind_migration_preserves_references(tmp_path):
    path=tmp_path/'old.sqlite'
    with closing(connect(path)) as connection:
        connection.executescript(SCHEMA_SQL.replace(", 'validation'",''))
        connection.execute(
            "INSERT INTO jobs(id,kind,status,created_at) "
            "VALUES ('old','batch_prediction','SUCCESS','2025')")
        connection.execute(
            "INSERT INTO prediction_results(job_id,status,created_at) "
            "VALUES ('old','SUCCESS','2025')")
        connection.commit()
        ensure_schema(connection)
        assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert connection.execute('PRAGMA user_version').fetchone()[0]==7
    assert JobRepository(path).get_job('old')['status']=='SUCCESS'
    assert len(PredictionResultRepository(path).list_results('old'))==1
    assert JobRepository(path).insert_job(kind='validation',details={'validation_mode':'random'})
