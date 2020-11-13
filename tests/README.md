rhizo-server test suite
=======================

This directory contains the automated test suite for the server.

The tests are not all unit tests per se; many of them perform database operations. The test suite can be run against both SQLite3 and PostgreSQL.

## Setup

1. Run `pip install -r tests/requirements.txt` to install pytest and required test modules.
2. (Optional) Run `pip install -r tests/requirements-postgres.txt` to install modules for testing against PostgreSQL. This requires that you have PostgreSQL installed locally.

## Running the tests

Run `pytest`. By default, the tests run against an in-memory SQLite database.

To test against PostgreSQL, set the `TEST_DATABASE` environment variable to `postgres`. Easiest is to set it for just the `pytest` command:

    TEST_DATABASE=postgres pytest

PostgreSQL-backed tests do not require any database setup; the test suite launches its own PostgreSQL server with a temporary data directory and removes the data afterwards.

**NOTE!** If you kill a PostgreSQL-backed test rather than letting it finish, the temporary PostgreSQL server processes may not be properly cleaned up. You will need to kill them manually.

## Things to know when writing tests

### Database

Database-backed tests run in transactions that get rolled back after each test function, so tests don't have to worry about cleaning up anything they insert.

### Fixtures

The tests make heavy use of [pytest fixtures](https://docs.pytest.org/en/stable/fixture.html) to set up the initial database state. The idea is that a test method can declare the kinds of sample data it needs, and the fixtures will take care of inserting all the dependent rows.

For example, if a test needs a `Key` resource, it implicitly needs a `User` to own the key, and the `User` implicitly needs an `Organization` to belong to. The test function just needs to declare the `Key` as a parameter and the other tables will be initialized as well.

If the test method is only declaring a fixture dependency for its side effects and is never actually using the fixture object, it should use a `@pytest.mark.usefixtures` decorator instead of a parameter.

As a pleasant side effect, this reduces the amount of module importing that needs to happen in test functions, since they can just ask for the model objects (by declaring the fixtures as parameters).

### Classes

The test suite uses a mix of top-level functions and classes.

Classes are used in part to reduce repetitive fixture declaration. That is, if you have 10 semantically-related test functions that all need the same set of fixtures, it's cleaner to put them in a class that has a setup method that takes the fixtures as arguments and stores them in `self`.

If the class only needs a fixture for its side effects and will never use the fixture object, add a `@pytest.mark.usefixtures` decorator to the class and list the fixture there.

If you do that, just decorate the setup function with `@pytest.fixture(autouse=True)` and pytest will call it automatically.

### Flask

Many tests are integration tests that exercise the Flask endpoints rather than calling the business logic directly. The `api` fixture is initialized with the same URL paths as the real server, e.g., `/api/v1/resources`. Tests can use the standard Flask test client class to simulate API calls and examine the responses.

One thing to be aware of because it can cause occasional side effects is that because Flask apps, by convention, do initialization at the top level, some of the setup in `main/app.py` ends up getting run during import and then discarded in order to substitute test fixtures. The typical context where you'll notice this is if your test does `from main.app import app` -- depending on exactly when the import happens, you might get a copy of `app` with the wrong database configuration. To avoid that, have your test function declare an `app` parameter and it will be passed a correctly configured `Flask` object.
