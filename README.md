## README

### Docker

- docker build -t dockertest .
- docker run -e BASE_PATH=/data -v ~/dockertest:/data dockertest -d dois.json

### Local

- export BASE_PATH=~/dockertest
- python app/main.py -d dois.json