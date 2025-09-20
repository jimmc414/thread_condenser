from celery import Celery

from app.config import settings

celery_app = Celery("tc", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.task_queues = {
    "default": {},
    "webhooks": {},
    "sync": {},
    "digest": {},
}
celery_app.conf.task_default_queue = "default"
celery_app.conf.result_expires = 3600
