# Bootloader Handler

The `bootloader_handler` tool provides access to the bootloader and firmware update of the Spektralwerk.

The Spektralwerk must be available and reachable from the host (e.g. same network domain).

## Actions

The available actions are:

- access bootloader context
- access application context
- upload firmware-releases

In general switching the context takes several minutes.
Please be patient.

### Access Bootloader Context

The bootloader context allows firmware modifications.
To access the bootloader context, use the provided `hatch` script:

```sh
hatch run tools:bootloader -- enter-bootloader
```

The SCPI interface is used to access the bootloader but once the bootloader context is available, the SCPI interface is not reachable any more.

### Access Application Context
