# Pure Storage //X50 R4 Admin Query Tool

A command-line utility for querying Pure Storage FlashArray systems. Extracts infrastructure data including arrays, hardware, networking, volumes, and hosts.

## Installation Requirements

- Python 3.x with `requests` and `urllib3` 
- A valid `pure.json` configuration file in the same directory, see the portworx documentation

## Usage

```bash
python3 px_pure_fax50r4_query.py [OPTIONS]
```

### Configuration File

The tool reads connection credentials from `pure.json`:

```json
{
  "FlashArrays": [
    {
      "MgmtEndPoint": "pfs-01.example.com",
      "APIToken": "your_api_token_here"
    }
  ]
}
```

### Commands

| Flag | Description |
|------|-------------|
| `--arraylist` | List all arrays with capacity and version info |
| `--hardwarelist` | List hardware components with status |
| `--hostlist` | List hosts with their IQN values |
| `--volumelist` | List volumes with host connections |
| `--subnetlist` | List network subnets and VLANs |
| `--interfacelist` | List network interfaces and services |

### Options

- `--debug` - Enable debug logging mode
- `--unmasked-tokens` - Show unmasked tokens in debug output
- `--grep <TERM>` - Filter output while keeping headers

## Examples

```bash
# List all array information
python3 px_pure_fax50r4_query.py --arraylist

# List hardware with debug mode
python3 px_pure_fax50r4_query.py --hardwarelist --debug

# List volumes filtered by connection type
python3 px_pure_fax50r4_query.py --volumelist --grep iqn.20XX.xxxx.example
```

## Files

- `px_pure_fax50r4_query.py` - Main application script
