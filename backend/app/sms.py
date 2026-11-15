"""SMS simulation. No real gateway: every alert SMS is written to sms_outbox (status 'simulated')
exactly as it would be sent, and the UI shows it in a phone inbox."""
from .db import tx

MAX_LEN = 459  # 3 GSM-7 segments


def send(user_id: int, phone: str, body: str) -> str:
    status = "simulated" if phone else "no_phone"
    with tx() as con:
        con.execute("INSERT INTO sms_outbox(user_id, phone, body, provider, status) VALUES(?,?,?,?,?)",
                    (user_id, phone, body[:MAX_LEN], "simulation", status))
    return status
