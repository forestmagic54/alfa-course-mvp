# Test rules

- Do not add tests that merely restate fixed values or simple constraints in code, static data, or configuration, or repeat standard library behavior; use existing validators for static data and configuration. Add tests only for concrete risks in application behavior, preferably by extending existing tests.
- Test configuration when a failure could affect application behavior or security, including configuration passed between components, handling secrets and special characters, resource cleanup, and session isolation.

- Use pytest for unit tests.
- Do not add integration tests or Testcontainers for now; unit tests must not require a running database or external services.
- Run new and modified tests when needed, using concise output and relevant tracebacks (`pytest -q --tb=short`); stop after two failed attempts.
