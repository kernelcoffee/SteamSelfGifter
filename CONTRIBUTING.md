# Contributing to SteamSelfGifter

Thank you for considering contributing to SteamSelfGifter!

## Getting Started

1. Fork the repository
2. Clone your fork
3. Set up development environment (see README.md)
4. Create a feature branch
5. Make your changes
6. Submit a pull request

## Development Setup

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest  # Verify setup
```

### Frontend
```bash
cd frontend
npm install
npm test  # Verify setup
```

## Guidelines

### Code Style

- **Python**: Follow PEP 8, use type hints
- **TypeScript**: Use strict mode, define interfaces

### Pull Requests

- One feature/fix per PR
- Include tests for new functionality
- Update documentation if needed
- Keep commits focused and well-described

### Commit Messages

Use clear, descriptive commit messages:
```
Add safety check toggle to settings page
Fix timezone handling in giveaway end times
Update API documentation for new endpoints
```

## Testing

### Backend
```bash
cd backend
pytest                # All tests
pytest --cov=src      # With coverage
```

### Frontend
```bash
cd frontend
npm test              # All tests
npm run test:coverage # With coverage
```

## Reporting Issues

- Check existing issues first
- Include reproduction steps
- Provide environment details (OS, Python/Node version)

## Security

If you find a security vulnerability, please email the maintainer directly instead of opening a public issue.

## Questions?

Open an issue for questions or discussion.
