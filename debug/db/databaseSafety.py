LOCAL_MONGO_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
    }
)
TEST_DATABASE_NAME = "sortMasterTest"


def requireLocalTestDatabase(
    mongoHost: str,
    databaseName: str,
) -> None:
    normalizedHost = mongoHost.strip().lower()

    if (
        normalizedHost not in LOCAL_MONGO_HOSTS
        or databaseName != TEST_DATABASE_NAME
    ):
        raise RuntimeError(
            "This debug script only accepts a local MongoDB "
            f"({sorted(LOCAL_MONGO_HOSTS)}) with "
            f"DB_NAME={TEST_DATABASE_NAME}. "
            f"Received MONGO_HOST={mongoHost!r}, "
            f"DB_NAME={databaseName!r}."
        )
