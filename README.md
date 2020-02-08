# SteamSelfGifter
Bot for SteamGifts


## Dev

```
virtualenv -p python3 env
source env/bin/activate
pip3 install -r requirements/test.txt
```

## Run

```bash
python steamselfgifter/steamselfgifter.py -c <path_to_config.ini>
```

or

```bash
SESSIONID=<PHPSESSID> python steamselfgifter/steamselfgifter.py
```

## Docker

Build & run Docker image
```bash
docker build -t steamselfgifter .
docker run -d -v /path/to/config/folder:/config --name steamselfgifter steamselfgifter

```

docker-compose

You can either use the environment variables or the config file

```
  steamselfgifter:
    container_name: steamselfgifter
    image: kernelcoffee/steamselfgifter
    environment:
      LOGGING: "INFO"
      PHPSESSID: <PHPSESSID>
    volumes:
      - /path/to/config/folder:/config

```

## Variables:
`LOGGING`: "INFO" or "DEBUG"
`PHPSESSID`: SessionID extract from steamgifts

## How to get your PHPSESSID
- Sign in on steamgifts.com.
- Extract the PHPSESSID cookie from your browser, you can use your browser's dev tools for it
