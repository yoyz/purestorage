#!/usr/bin/python3
import requests
import json
import urllib3
import argparse
import sys
import io

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEBUG_MODE = False
UNMASK_TOKENS = False
GREP_TERM = None

def log_debug(method, url, headers, response_text):
    if DEBUG_MODE:
        curl_headers = ""
        for k, v in headers.items():
            display_val = v if UNMASK_TOKENS or ("token" not in k.lower()) else "********"
            curl_headers += f"-H '{k}: {display_val}' "
        print(f"\n[DEBUG] curl -k -X {method} {curl_headers}'{url}'")
        print(f"[DEBUG] RAW RESPONSE: {response_text}")
        print("-" * 30)

def smart_print(text):
    """
    Filters output based on GREP_TERM while preserving headers.
    Headers are identified as the first 2 lines of any block of text.
    """
    if not GREP_TERM:
        print(text)
        return

    lines = text.splitlines()
    if not lines:
        return

    output = []
    # Always keep the first two lines (Header and the separator dashes)
    if len(lines) >= 1: output.append(lines[0])
    if len(lines) >= 2: output.append(lines[1])

    # Filter the rest of the lines
    for line in lines[2:]:
        if GREP_TERM.lower() in line.lower():
            output.append(line)
    
    print("\n".join(output))

def load_config():
    try:
        with open('pure.json', 'r') as f:
            config = json.load(f)
            fa = config['FlashArrays'][0]
            return fa['MgmtEndPoint'], fa['APIToken']
    except Exception as e:
        print(f"❌ Error reading pure.json: {e}")
        sys.exit(1)

def get_session(host, token, api_ver="2.3"):
    base_url = f"https://{host}/api/{api_ver}"
    session = requests.Session()
    session.verify = False 
    url = f"{base_url}/login"
    headers = {'Content-Type': 'application/json', 'api-token': token}
    try:
        res = session.post(url, headers=headers)
        log_debug("POST", url, headers, res.text)
        res.raise_for_status()
        session.headers.update({'x-auth-token': res.headers.get('x-auth-token')})
        if not DEBUG_MODE and not GREP_TERM: 
            print(f"✅ Connected to {host} (API {api_ver})")
        return session, base_url
    except Exception as e:
        print(f"❌ Login Error on API {api_ver}: {e}")
        sys.exit(1)

def list_array(session, base_url):
    url = f"{base_url}/arrays"
    try:
        res = session.get(url)
        res.raise_for_status()
        data = res.json()
        out = io.StringIO()
        out.write(f"{'ARRAY NAME':<20} {'VERSION':<10} {'CAPACITY (TiB)':<15} {'REDUCTION'} {'THIN %'}\n")
        out.write("-" * 75 + "\n")
        for item in data.get('items', []):
            space = item.get('space', {})
            out.write(f"{item.get('name'):<20} {item.get('version'):<10} {item.get('capacity', 0)/(1024**4):<15.2f} {space.get('data_reduction', 0):<10.1f} {space.get('thin_provisioning', 0)*100:<5.1f}%\n")
        smart_print(out.getvalue())
    except Exception as e:
        print(f"❌ Failed to list array: {e}")

def list_hardware(session, base_url):
    url = f"{base_url}/hardware"
    try:
        res = session.get(url)
        res.raise_for_status()
        out = io.StringIO()
        out.write(f"{'NAME':<15} {'TYPE':<15} {'STATUS':<8} {'SPEED':<12} {'TEMP'}\n")
        out.write("-" * 65 + "\n")
        for item in res.json().get('items', []):
            speed = f"{item.get('speed')/1e9:.1f} Gbps" if item.get('speed') else "N/A"
            temp = f"{item.get('temperature')}°C" if item.get('temperature') else "N/A"
            out.write(f"{item.get('name'):<15} {item.get('type'):<15} {item.get('status'):<8} {speed:<12} {temp}\n")
        smart_print(out.getvalue())
    except Exception as e:
        print(f"❌ Failed to list hardware: {e}")

def list_interfaces(host, token):
    session, base_url = get_session(host, token, api_ver="2.5")
    url = f"{base_url}/network-interfaces"
    try:
        res = session.get(url)
        log_debug("GET", url, session.headers, res.text)
        res.raise_for_status()
        out = io.StringIO()
        out.write(f"{'INTERFACE':<15} {'IP ADDRESS':<18} {'MAC ADDRESS':<20} {'SERVICES':<15} {'STATUS'}\n")
        out.write("-" * 90 + "\n")
        for item in res.json().get('items', []):
            eth = item.get('eth', {})
            name = item.get('name', 'N/A')
            addr = eth.get('address') or "None"
            mac = eth.get('mac_address') or "N/A"
            svcs = ", ".join(item.get('services', [])) if item.get('services') else "None"
            status = "Enabled" if item.get('enabled') else "Disabled"
            out.write(f"{name:<15} {addr:<18} {mac:<20} {svcs:<15} {status}\n")
        smart_print(out.getvalue())
    except Exception as e:
        print(f"❌ Failed to list interfaces: {e}")

def list_subnets(session, base_url):
    url = f"{base_url}/subnets"
    try:
        res = session.get(url)
        res.raise_for_status()
        out = io.StringIO()
        out.write(f"{'SUBNET NAME':<25} {'PREFIX':<18} {'VLAN':<6} {'MTU':<6} {'SERVICES'}\n")
        out.write("-" * 80 + "\n")
        for item in res.json().get('items', []):
            svcs = ", ".join(item.get('services', [])) if item.get('services') else "None"
            out.write(f"{item.get('name'):<25} {item.get('prefix'):<18} {item.get('vlan'):<6} {item.get('mtu'):<6} {svcs}\n")
        smart_print(out.getvalue())
    except Exception as e:
        print(f"❌ Failed to list subnets: {e}")

def list_hosts(session, base_url):
    url = f"{base_url}/hosts"
    try:
        res = session.get(url)
        res.raise_for_status()
        out = io.StringIO()
        out.write(f"{'HOST NAME':<45} {'IQN'}\n")
        out.write("-" * 110 + "\n")
        for host in res.json().get('items', []):
            iqns = ", ".join(host.get('iqns', [])) if host.get('iqns') else "N/A"
            out.write(f"{host.get('name'):<45} {iqns}\n")
        smart_print(out.getvalue())
    except Exception as e:
        print(f"❌ Failed to list hosts: {e}")

def list_volumes(session, base_url):
    try:
        v_res = session.get(f"{base_url}/volumes").json()
        c_res = session.get(f"{base_url}/connections").json()
        conns = {}
        for item in c_res.get('items', []):
            conns.setdefault(item.get('volume', {}).get('name'), []).append(item.get('host', {}).get('name'))
        out = io.StringIO()
        out.write(f"{'VOLUME NAME':<65} {'SIZE (GiB)':<10} {'CONNECTED HOSTS'}\n")
        out.write("-" * 125 + "\n")
        for vol in v_res.get('items', []):
            name = vol.get('name')
            out.write(f"{name:<65} {vol.get('provisioned', 0)/(1024**3):<10.1f} {', '.join(conns.get(name, ['None']))}\n")
        smart_print(out.getvalue())
    except Exception as e:
        print(f"❌ Failed to list volumes: {e}")

def main():
    global DEBUG_MODE, UNMASK_TOKENS, GREP_TERM
    parser = argparse.ArgumentParser(description="Pure Storage //X50 R4 Admin Tool")
    parser.add_argument('--arraylist', action='store_true')
    parser.add_argument('--hardwarelist', action='store_true')
    parser.add_argument('--hostlist', action='store_true')
    parser.add_argument('--volumelist', action='store_true')
    parser.add_argument('--subnetlist', action='store_true')
    parser.add_argument('--interfacelist', action='store_true')
    parser.add_argument('--grep', type=str, help='Filter output while keeping headers')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--unmasked-tokens', action='store_true')
    
    args = parser.parse_args()
    if args.debug: DEBUG_MODE = True
    if args.unmasked_tokens: UNMASK_TOKENS = True
    if args.grep: GREP_TERM = args.grep

    if not any([args.arraylist, args.hardwarelist, args.hostlist, args.volumelist, args.subnetlist, args.interfacelist]):
        parser.print_help(); sys.exit(0)

    mgmt_host, api_token = load_config()

    if args.interfacelist:
        list_interfaces(mgmt_host, api_token)
    
    if any([args.arraylist, args.hardwarelist, args.hostlist, args.volumelist, args.subnetlist]):
        session, base_url = get_session(mgmt_host, api_token)
        if args.arraylist: list_array(session, base_url)
        if args.hardwarelist: list_hardware(session, base_url)
        if args.subnetlist: list_subnets(session, base_url)
        if args.hostlist: list_hosts(session, base_url)
        if args.volumelist: list_volumes(session, base_url)

if __name__ == "__main__":
    main()
