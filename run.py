from datetime import datetime
from app import create_app, mail
from apscheduler.schedulers.background import (
    BackgroundScheduler
)

app = create_app()

def run_alerts():
    from alerts.alert_engine import check_and_send_alerts
    check_and_send_alerts(app, mail)

# Store on app so routes.py can trigger it without re-importing run.py
app.run_alerts = run_alerts

# Guard: only start scheduler in the main process, never twice
import os
if not os.environ.get('SCHEDULER_STARTED'):
    os.environ['SCHEDULER_STARTED'] = '1'
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_alerts,
        'interval',
        minutes=15,
        id='alert_checker',
        next_run_time=datetime.now()  # fire immediately on app start
    )
    scheduler.start()
    print("[Scheduler] Started — alert engine runs every 15 minutes.")
else:
    print("[Scheduler] Already running, skipping duplicate start.")

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)