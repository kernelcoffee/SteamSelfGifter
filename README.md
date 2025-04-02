# SteamSelfGifter

[![Python Version](https://img.shields.io/badge/python-3.13.2-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

SteamSelfGifter is an automated bot for entering Steam game giveaways on SteamGifts.com. It helps you automatically enter giveaways for games you want based on various criteria, including your wishlist, DLC preferences, and customizable auto-join settings.

## Features

- 🎮 **Wishlist Integration**: Automatically enters giveaways for games on your SteamGifts wishlist
- 🎯 **DLC Support**: Optional support for DLC giveaways
- 🤖 **Smart Auto-join**: Automatically enters other giveaways based on customizable criteria:
  - Minimum price threshold
  - Minimum review score
  - Minimum number of reviews
- ⚡ **Rate Limiting**: Built-in delays to avoid detection
- 🔄 **Duplicate Prevention**: Prevents entering the same giveaway multiple times
- 🐳 **Docker Support**: Easy deployment using Docker or Docker Compose

## Prerequisites

- Python 3.13.2 or higher
- SteamGifts account
- PHPSESSID from SteamGifts (see [How to get your PHPSESSID](#how-to-get-your-phpsessid))

## Installation

### Local Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/SteamSelfGifter.git
   cd SteamSelfGifter
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv env
   source env/bin/activate  # On Windows: env\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements/test.txt
   ```

4. Copy the sample configuration:
   ```bash
   cp config.ini.sample config.ini
   ```

5. Edit `config.ini` with your settings (see [Configuration](#configuration))

### Docker Installation

1. Build the Docker image:
   ```bash
   docker build -t steamselfgifter .
   ```

2. Run the container:
   ```bash
   docker run -d -v /path/to/config/folder:/config --name steamselfgifter steamselfgifter
   ```

### Docker Compose

Add the following to your `docker-compose.yml`:
```yaml
steamselfgifter:
  container_name: steamselfgifter
  image: kernelcoffee/steamselfgifter
  volumes:
    - /path/to/config/folder:/config
```

## Usage

Run the bot:
```bash
python steamselfgifter/steamselfgifter.py -c config.ini
```

## Configuration

Copy `config.ini.sample` to `config.ini` and configure the following sections:

### Network Settings
- `PHPSESSID`: Your SteamGifts session ID
- `user-agent`: Your browser's user agent string

### DLC Settings
- `enabled`: Enable/disable DLC giveaway entries

### Auto-join Settings
- `enabled`: Enable/disable automatic joining of non-wishlist giveaways
- `start_at`: Points threshold to start auto-joining
- `stop_at`: Points threshold to stop auto-joining
- `min_price`: Minimum game price to consider
- `min_score`: Minimum review score to consider
- `min_reviews`: Minimum number of reviews to consider

### Misc Settings
- `log_level`: Logging level (INFO, DEBUG, etc.)

## How to get your PHPSESSID

1. Sign in to [SteamGifts](https://www.steamgifts.com)
2. Open your browser's developer tools (F12)
3. Go to the Application/Storage tab
4. Look for Cookies under Storage
5. Find the `PHPSESSID` cookie value
6. Copy this value to your `config.ini`

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This bot is for educational purposes only. Please ensure you comply with SteamGifts' terms of service and use this tool responsibly.

## Support

If you encounter any issues or have questions, please open an issue in the GitHub repository.
