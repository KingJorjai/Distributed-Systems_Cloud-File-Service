# Offline Kit

The offline kit is a single ZIP for Ubuntu 22.04 containing the portable
server and desktop client. It needs no Internet and no Python installation.

Build it from the repository after building the demo bundles:

```sh
scripts/build_demo_bundles.sh
scripts/build_offline_kit.sh
```

The result is `demo/CloudFS-Offline-0.12.0-linux-x64.zip`.

## What it contains

```text
CloudFS/
  cloudfs
  _internal/
  config/
  certs/
  data/
  state/
  logs/
  packaging/
  docs/
    installation.pdf
    lab-walkthrough.pdf
  README.txt
```

There are no `.desktop` launchers and no `start-*.sh` scripts. The single
`cloudfs` binary provides `setup`, `server`, `client` and `status`.

## First run

Extract the ZIP, open a terminal in the `CloudFS` folder and run:

```sh
./cloudfs setup
```

`setup` creates the configuration, the CA and the server certificate, the
data and state directories, and the administrator account. It prints the
administrator credentials; save them.

Then start the server and the client:

```sh
./cloudfs server          # terminal 1
./cloudfs client          # terminal 2
```

## Cluster (three machines)

```sh
./cloudfs setup --cluster 192.168.1.101,192.168.1.102,192.168.1.103
```

Copy each `cluster/serverN` directory to its machine and run
`./cloudfs server --config serverN/config.toml`.

## Verify

```sh
./cloudfs status
```

## Certificates

`setup` generates a private CA and a server certificate with the addresses
you provide (or the detected address plus `localhost`). The client trusts the
CA automatically. The admin browser shows the normal private-CA warning unless
you import `certs/ca.crt`.

## Logs

Server and daemon logs are written to `logs/`:

- `logs/server.log`
- `logs/daemon.log`
- `logs/gui.log`

The GUI has an **Abrir logs** button. Logs rotate at 5 MiB with three backups.

## Size and email

The ZIP is self-contained and has no external download step. Keep it below
the mail attachment limit; do not add development files, databases or test
data.
