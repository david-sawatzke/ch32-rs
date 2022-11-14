#!/usr/bin/env python3

"""
makecrates.py
Copyright 2017-2019 Adam Greig
Copyright 2022 Andelf <andelf@gmail.com>
Licensed under the MIT and Apache 2.0 licenses.

Autogenerate the crate Cargo.toml, build.rs, README.md and src/lib.rs files
based on available YAML files for each CH32 family.

Usage: python3 scripts/makecrates.py devices/
"""

import os
import glob
import os.path
import argparse
import re

VERSION = "0.1.4"
SVD2RUST_VERSION = "0.26.0"

CRATE_DOC_FEATURES = {
    "ch32v3": ["rt", "ch32v30x"],
    "ch32v2": ["rt", "ch32v20x"],
    "ch32v1": ["rt", "ch32v103"],
    "ch58x": ["rt", "ch58x"],
}

CRATE_DOC_TARGETS = {
    "ch32v3": "riscv32imac-unknown-none-elf",
    "ch32v2": "riscv32imac-unknown-none-elf",
    "ch32v1": "riscv32imac-unknown-none-elf",
    "ch58x": "riscv32imac-unknown-none-elf",
}

CARGO_TOML_TPL = """\
[package]
edition = "2021"
name = "{crate}"
version = "{version}"
authors = ["Andelf <andelf@gmail.com>", "ch32-rs Contributors"]
description = "Device support crates for {family} devices"
repository = "https://github.com/ch32-rs/ch32-rs"
readme = "README.md"
keywords = ["wch", "ch32", "svd2rust", "no_std", "embedded"]
categories = ["embedded", "no-std", "hardware-support"]
license = "MIT/Apache-2.0"

[dependencies]
riscv = "0.10.0"
riscv-rt = {{ version = "0.10.0", optional = true }}
vcell = "0.1.0"

[package.metadata.docs.rs]
features = {docs_features}
default-target = "{doc_target}"
targets = []

[features]
default = []
rt = ["riscv-rt"]
{features}
"""

SRC_LIB_RS_TPL = """\
//! Peripheral access API for {family} microcontrollers
//! (generated using [svd2rust](https://github.com/rust-embedded/svd2rust)
//! {svd2rust_version})
//!
//! You can find an overview of the API here:
//! [svd2rust/#peripheral-api](https://docs.rs/svd2rust/{svd2rust_version}/svd2rust/#peripheral-api)
//!
//! For more details see the README here:
//! [ch32-rs](https://github.com/ch32-rs/ch32-rs)
//!
//! This crate supports all {family} devices; for the complete list please
//! see:
//! [{crate}](https://crates.io/crates/{crate})
//!

#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![no_std]

mod generic;
pub use self::generic::*;

{mods}
"""

README_TPL = """\
# {crate}
This crate provides an autogenerated API for access to {family} peripherals.
The API is generated using [svd2rust] with patched svd files containing
extensive type-safe support. For more information please see the [main repo].

Refer to the [documentation] for full details.

[svd2rust]: https://github.com/rust-embedded/svd2rust
[main repo]: https://github.com/ch32-rs/ch32-rs
[documentation]: https://docs.rs/{crate}/latest/{crate}/

## Usage
Each device supported by this crate is behind a feature gate so that you only
compile the device(s) you want. To use, in your Cargo.toml:

```toml
[dependencies.{crate}]
version = "{version}"
features = ["{device}"]
```

The `rt` feature is enabled by default and brings in support for `riscv-rt`.
To disable, specify `default-features = false` in `Cargo.toml`.

In your code:

```rust
use {crate}::{device};

let mut peripherals = {device}::Peripherals::take().unwrap();
let gpioa = &peripherals.GPIOA;
gpioa.odr.modify(|_, w| w.odr0().set_bit());
```

For full details on the autogenerated API, please see:
https://docs.rs/svd2rust/{svd2rust_version}/svd2rust/#peripheral-api

## Supported Devices

| Module | Devices | Links |
|:------:|:-------:|:-----:|
{devices}
"""


BUILD_TPL = """\
use std::env;
use std::fs;
use std::path::PathBuf;
fn main() {{
    if env::var_os("CARGO_FEATURE_RT").is_some() {{
        let out = &PathBuf::from(env::var_os("OUT_DIR").unwrap());
        println!("cargo:rustc-link-search={{}}", out.display());
        let device_file = {device_clauses};
        fs::copy(device_file, out.join("device.x")).unwrap();
        println!("cargo:rerun-if-changed={{}}", device_file);
    }}
    println!("cargo:rerun-if-changed=build.rs");
}}
"""


def make_features(devices):
    return "\n".join("{} = []".format(d) for d in sorted(devices))


def make_mods(devices):
    return "\n".join('#[cfg(feature = "{0}")]\npub mod {0};\n'.format(d)
                     for d in sorted(devices))


def make_device_clauses(devices):
    return " else ".join("""\
        if env::var_os("CARGO_FEATURE_{}").is_some() {{
            "src/{}/device.x"
        }}""".strip().format(d.upper(), d) for d in sorted(devices)) + \
            " else { panic!(\"No device features selected\"); }"


def main(devices_path, yes, families):
    devices = {}

    for path in glob.glob(os.path.join(devices_path, "*.yaml")):
        yamlfile = os.path.basename(path)
        if "ch5" in yamlfile:
            family = yamlfile.split('.')[0]
        else:
            family = re.match(r'ch32[a-z]*[0-9]', yamlfile)[0]

        if family == 'ch32v0':
            continue # skip for now


        device = os.path.splitext(yamlfile)[0].lower()
        if len(families) == 0 or family in families:
            if family not in devices:
                devices[family] = []
            devices[family].append(device)


    dirs = ", ".join(x.lower()+"/" for x in devices)
    print("Going to create/update the following directories:")
    print(dirs)
    if not yes:
        input("Enter to continue, ctrl-C to cancel")

    for family in devices:
        devices[family] = sorted(devices[family])
        crate = family.lower()
        features = make_features(devices[family])
        clauses = make_device_clauses(devices[family])
        mods = make_mods(devices[family])
        ufamily = family.upper()
        cargo_toml = CARGO_TOML_TPL.format(
            family=ufamily, crate=crate, version=VERSION, features=features,
            docs_features=str(CRATE_DOC_FEATURES[crate]),
            doc_target=CRATE_DOC_TARGETS[crate])
        readme = README_TPL.format(
            family=ufamily, crate=crate, device=devices[family][0],
            version=VERSION, svd2rust_version=SVD2RUST_VERSION,
            devices="") # TODO: get devices
        lib_rs = SRC_LIB_RS_TPL.format(family=ufamily, mods=mods, crate=crate,
                                       svd2rust_version=SVD2RUST_VERSION)
        build_rs = BUILD_TPL.format(device_clauses=clauses)

        os.makedirs(os.path.join(crate, "src"), exist_ok=True)

        with open(os.path.join(crate, "Cargo.toml"), "w") as f:
            f.write(cargo_toml)
        with open(os.path.join(crate, "README.md"), "w") as f:
            f.write(readme)
        with open(os.path.join(crate, "src", "lib.rs"), "w") as f:
            f.write(lib_rs)
        with open(os.path.join(crate, "build.rs"), "w") as f:
            f.write(build_rs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-y",
                        help="Assume 'yes' to prompt",
                        action="store_true")
    parser.add_argument("devices",
                        help="Path to device YAML files")
    parser.add_argument('--families',
                        help="Families of components to generate crates for",
                        nargs='+',
                        required=False,
                        metavar='FAMILY',
                        default=[],
                        type=str)
    args = parser.parse_args()
    main(args.devices, args.y, args.families)
