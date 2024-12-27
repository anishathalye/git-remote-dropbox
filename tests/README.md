# Testing

When running tests locally, git-remote-dropbox uses [Vagrant] to run tests
inside a virtual machine to completely isolate tests from the host machine.

## Running the tests

Start the VM using `vagrant up`, and SSH into the VM using `vagrant ssh`. The
rest of the commands should be run in the VM.

The test script requires a Dropbox token to run, because it actually interacts
with the real Dropbox API during the test.

```bash
cd /git-remote-dropbox
pip3 install -e .
cd test
export DROPBOX_TOKEN='...'
./test.sh
```

[Vagrant]: https://www.vagrantup.com/
