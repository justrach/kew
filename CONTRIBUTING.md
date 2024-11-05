# Contributing to Kew

First off, thanks for taking the time to contribute! 🎉 

Kew is a community project and every contribution helps make it better. Whether you're fixing a bug, adding a feature, or improving documentation, your help is welcome.

## Getting Started

1. Fork the repository
2. Clone your fork:
```bash
git clone https://github.com/justrach/kew.git
cd kew
```

3. Set up your development environment:
```bash
# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

# Install development dependencies
pip install -e ".[dev]"
```

4. Start Redis (required for running tests):
```bash
docker run -d -p 6379:6379 redis:alpine
```

## Development Workflow

1. Create a new branch for your changes:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes

3. Run the test suite:
```bash
pytest tests/
```

4. Format your code:
```bash
black kew/
isort kew/
```

5. Run the linter:
```bash
flake8 kew/
```

## Testing

We use pytest for our test suite. All new features should include tests. To run tests:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_specific.py

# Run with coverage report
pytest --cov=kew tests/
```

### Test Requirements

- All tests must pass
- Coverage should not decrease
- New features must include tests
- Tests should include both success and error cases

## Code Style

We follow PEP 8 with some modifications:
- Line length: 88 characters (Black default)
- Use double quotes for strings
- Use explicit type hints where beneficial

We use these tools to maintain code quality:
- Black for code formatting
- isort for import sorting
- flake8 for linting

## Pull Request Process

1. Update the README.md with details of your changes if needed
2. Update the docs/ folder with any new documentation
3. Add or update tests as needed
4. Update the CHANGELOG.md following the Keep a Changelog format
5. Submit your pull request

### PR Requirements

- Clear description of changes
- Tests pass
- Code formatted with Black
- No linting errors
- Documentation updated if needed
- CHANGELOG.md updated

## Commit Messages

We follow the conventional commits specification. Each commit message should have a type:

```
feat: Add new feature
fix: Fix bug
docs: Update documentation
test: Add tests
chore: Update tooling or dependencies
```

Example:
```
feat: Add circuit breaker reset timeout configuration

- Add reset_timeout parameter to QueueConfig
- Update documentation
- Add tests for timeout behavior
```

## Documentation

If you're adding new features, please include:
- Docstrings for new functions/classes
- Updates to the relevant docs/ files
- Examples in the README if appropriate

## Need Help?

If you're not sure about something:
1. Check existing issues and pull requests
2. Open an issue to discuss major changes
3. Ask questions in the pull request

## Types of Contributions

### Bug Reports

Please include:
- Python version
- Kew version
- Minimal code to reproduce
- Expected vs actual behavior

### Feature Requests

Please include:
- Use case description
- Example code showing desired API
- Explanation of why it's useful

### Code Contributions

We especially welcome:
- Bug fixes
- Performance improvements
- Documentation improvements
- New features
- Test improvements

## Development Environment Tips

### Running Redis Locally
```bash
# Using Docker
docker run -d -p 6379:6379 redis:alpine

# Or install locally
sudo apt-get install redis-server  # Ubuntu
brew install redis                 # macOS
```

### Useful Commands
```bash
# Run tests with output
pytest -v

# Format code
black kew/
isort kew/

# Check types
mypy kew/

# Build docs
cd docs/
make html
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.