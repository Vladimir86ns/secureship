import logging

logger = logging.getLogger("secureship.mock_sms")


def send_mock_sms(phone_number: str, code: str) -> None:
    """The entire mock SMS delivery mechanism: a clearly labeled log line.

    This is the one place identity-adjacent data (phone + the code itself) is
    permitted in application logs, since this line *is* the simulated SMS.
    Read it with `docker compose logs -f backend`.
    """
    logger.info("[MOCK SMS] to %s: Your SecureShip verification code is %s", phone_number, code)
