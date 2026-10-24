from app.ingest.scheduler import build_scheduler


def test_one_job_per_active_source_with_its_interval(session_factory, make_connectors):
    scheduler = build_scheduler(session_factory, make_connectors())
    jobs = {j.id: j for j in scheduler.get_jobs()}
    assert set(jobs) == {"prothomalo-bn", "prothomalo-en", "bdnews24-bn", "bdnews24-en"}
    assert jobs["prothomalo-en"].trigger.interval.total_seconds() == 10 * 60
    assert jobs["bdnews24-en"].trigger.interval.total_seconds() == 30 * 60
    assert all(j.max_instances == 1 for j in jobs.values())
