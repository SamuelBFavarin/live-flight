### This is the spec to create the Live Flight System

Goal: Based in my current location, show me the information of the closest flight information to me, like flight id, current speed, origin and destination. It must to be live data, that must to refresh every 20 seconds.

### Technologies

- Script must to be created in Python.
- It should consume the OpenSky API. The documentation is defined here: https://openskynetwork.github.io/opensky-api/python.html
- It should use environment variables (loaded from a `.env` file) to define the OpenSky OAuth2 credentials (`OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET`). `.env` must be excluded from version control.
- We need to setup a local environment using poetry


### Business Rules

- When system is opened, it should capture the current device location, get the lat and long information
- The system must to authenticate to the API using the OAuth2 client credentials (client id + client secret) defined in the environment variables
- Every 20 seconds the system should refresh the data, showing the closest flight
- It at least show the: flight identification, airline, aircraft model, origin, destination and speed
- The aircraft model and operating airline must to be derived from the aircraft's ICAO24 address using a public aircraft registry (e.g. `hexdb.io`); when the registry does not return a match, show `N/A`
- The information should be showed in the console, we don't need UI for this project


### Quality & Continuous Integration

- The project must to have unit tests covering the main business logic (location lookup, OpenSky client, console output), written with `pytest`
- Test coverage must to be tracked with `pytest-cov` and reported automatically when running the test suite
- A GitHub Actions workflow must to run the test suite on every push to the `main` branch, and the build should fail if any test fails
