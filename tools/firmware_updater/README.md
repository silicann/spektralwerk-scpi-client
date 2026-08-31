# Bootloader Handler

The `firmware_updater` tool provides access to the bootloader and firmware update of the Spektralwerk.

The Spektralwerk must be available and reachable from the host (e.g. same network domain).

## Actions

The available actions are:

- access bootloader context
- access application context
- get current firmware version
- upload firmware-releases

In general switching the context takes several minutes.
Please be patient.

Additional help can be obtained from `hatch run firmware-updater --help`

### Access Bootloader Context

The bootloader context allows firmware modifications.
To access the bootloader context, use the provided `hatch` script:

```sh
hatch run firmware-updater enter-bootloader
```

The SCPI interface is used to access the bootloader but once the bootloader context is available, the SCPI interface is not reachable any more.


### Access Application Context

The `hatch` script can be also used to leave the bootloader context and get back to application context:

```sh
hatch run firmware-updater enter-application
```

### Retrieve Current Firmware Version

The current Spektralwerk firmware version can be obtained using

```sh
hatch run firmware-updater get-firmware-version
```

### Update Spektralwerk Firmware

The Spektralwerk firmware can be updated.

```sh
hatch run firmware-updater --upload-file <FIRMWARE_FILE> update-firmware
```
