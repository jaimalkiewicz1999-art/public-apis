# Public APIs Scripts

This directory contains all validation and testing scripts used by Public APIs.

```bash
scripts
│   github_pull_request.sh  # used to validate changes of a pull request
│   requirements.txt  # contains dependencies of validate package
│
├───tests  # contains all unit tests from the validate package
│       test_validate_format.py
│       test_validate_links.py
│
└───validate  # validate package
        format.py
        links.py
        pr_diff.py  # extracts only the requested file's added diff lines
```

## Install dependencies

You must have [python](https://www.python.org/) installed to use these scripts.

it is also necessary to install the validation package dependencies, use [pip package manager](https://pypi.org/project/pip/) for this:

```bash
$ python -m pip install -r scripts/requirements.txt
```

## Run validations

To run format validation on the `README.md` file, being in the root directory of public-apis, run:

```bash
$ python scripts/validate/format.py README.md
```

To run link validation on the `README.md` file, being in the root directory of public-apis, run:

```bash
$ python scripts/validate/links.py README.md
```

As there are many links to check, this process can take some time. If your goal is not to check if the links are working, you can only check for duplicate links. Run:

```bash
$ python scripts/validate/links.py README.md -odlc
```

*`-odlc` is an abbreviation of `--only_duplicate_links_checker`*

## Running Tests

Pull-request validation downloads the complete PR diff, then extracts only added
lines from the requested file (normally `README.md`). Other files, diff metadata,
context and removed lines are excluded before the existing duplicate and HTTP
link checks. A PR with no README additions has no new links to validate; actual
duplicate README additions still fail. HTTP download errors fail the script.
Malformed or incomplete text diffs and binary target files also fail validation.
Git header separators are removed without changing filenames containing spaces
or quoted tabs. Quoted filenames preserve their original bytes, including raw
UTF-8 emitted by `core.quotePath=false`. Unrelated non-UTF-8 filenames, text,
context and removed lines do not prevent extraction; selected additions must
still be valid UTF-8, or validation fails without emitting partial output.

HTTP checks let the client generate the `Host` header for each request, including
redirects to a different host or port. Pinning the original host can cause false
redirect loops or errors from the destination. Terminal HTTP errors still fail
under the existing status and Cloudflare rules; the timeout remains 25 seconds.
Redirect tests use two loopback HTTP servers and verify both successful redirects
and failure responses without depending on public sites.

To run all tests it is necessary to change to the scripts directory:

```bash
$ cd scripts
```

then run:

```bash
$ python -m unittest discover tests/ --verbose
```

To run only the format tests, run:

```bash
$ python -m unittest discover tests/ --verbose --pattern "test_validate_format.py"
```

To run only the links tests, run:

```bash
$ python -m unittest discover tests/ --verbose --pattern "test_validate_links.py"
```
