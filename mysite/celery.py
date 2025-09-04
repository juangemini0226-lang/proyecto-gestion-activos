import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')

app = Celery('mysite')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Programa la importación de horómetro semanal (lunes 00:00)
app.conf.beat_schedule = {
    'importar-horometro-semanal': {
        'task': 'horometro.tasks.importar_horometro_task',
        'schedule': crontab(day_of_week='mon', hour=0, minute=0),
    }
}