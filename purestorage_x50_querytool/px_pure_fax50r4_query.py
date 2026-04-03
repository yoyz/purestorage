import requests
import json
import urllib3
import argparse
import sys
import re

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEBUG_MODE = False
UNMASK_TOKENS = False
GREP_TERM = None

def log_debug(method, url, headers, response):
    if DEBUG_MODE:
        curl_headers = "".join([f"-H '{k}: {v if UNMASK_TOKENS or 'token' not in k.lower() else '********'}' " for k, v in headers.items()])
        print(f"\n[DEBUG] curl -k -X {method} {curl_headers}'{url}'")
        if "login" in url or UNMASK_TOKENS:
            print(f"[DEBUG] RESPONSE HEADERS: {dict(response.headers)}")
        print(f"[DEBUG] RAW RESPONSE BODY: {response.text}\n" + "-"*30)

def safe_json(res):
    if res is not None and res.text.strip():
        try: return res.json()
        except: return {}
    return {}

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def smart_print(headers, rows):
    if not rows and not GREP_TERM:
        print("\n" + "  ".join(headers))
        print("-" * (sum(len(h) for h in headers) + len(headers)*2))
        print("No data found.")
        return

    filtered_rows = []
    for row in rows:
        line = " ".join([str(item) for item in row])
        if not GREP_TERM or GREP_TERM.lower() in line.lower():
            filtered_rows.append(row)

    if not filtered_rows:
        return

    col_widths = []
    for i, header in enumerate(headers):
        max_w = max([len(str(row[i])) for row in filtered_rows] + [len(header)])
        col_widths.append(max_w + 2) 

    fmt = "".join([f"{{:<{w}}}" for w in col_widths])
    
    print("\n" + fmt.format(*headers))
    print("-" * (sum(col_widths) - 1))
    
    for row in filtered_rows:
        print(fmt.format(*[str(item) for item in row]))

def load_config():
    try:
        with open('pure.json', 'r') as f:
            config = json.load(f)
            fa = config['FlashArrays'][0]
            return fa['MgmtEndPoint'], fa['APIToken']
    except Exception as e:
        print(f"❌ Error reading pure.json: {e}"); sys.exit(1)

def get_session(host, token):
    base_url = f"https://{host}/api/2.5"
    session = requests.Session()
    session.verify = False 
    url = f"{base_url}/login"
    headers = {'Content-Type': 'application/json', 'api-token': token}
    try:
        res = session.post(url, headers=headers)
        log_debug("POST", url, headers, res)
        res.raise_for_status()
        auth_token = res.headers.get('x-auth-token')
        if auth_token: session.headers.update({'x-auth-token': auth_token})
        if not DEBUG_MODE and not GREP_TERM: print(f"✅ Connected to {host} (API 2.5)")
        return session, base_url
    except Exception as e:
        print(f"❌ Login Error on API 2.5: {e}"); sys.exit(1)

# ==========================================
# Core Information Functions
# ==========================================

def list_array(session, base_url):
    try:
        res = session.get(f"{base_url}/arrays")
        log_debug("GET", f"{base_url}/arrays", session.headers, res)
        items = safe_json(res).get('items', [])
        headers = ["ARRAY_NAME", "VERSION", "CAPACITY(TiB)", "REDUCTION", "THIN%"]
        rows = [[i.get('name', 'N/A'), i.get('version', 'N/A'), f"{i.get('capacity', 0)/(1024**4):.2f}", 
                 f"{i.get('space', {}).get('data_reduction', 0):.1f}", f"{i.get('space', {}).get('thin_provisioning', 0)*100:.1f}%"] for i in items]
        rows.sort(key=lambda x: natural_sort_key(x[0]))
        smart_print(headers, rows)
    except Exception as e: print(f"❌ Array Error: {e}")

def list_hardware(session, base_url):
    try:
        res = session.get(f"{base_url}/hardware")
        log_debug("GET", f"{base_url}/hardware", session.headers, res)
        items = safe_json(res).get('items', [])
        headers = ["NAME", "TYPE", "STATUS", "INDEX", "SPEED", "TEMP", "SERIAL"]
        rows = []
        for i in items:
            speed = f"{int(i.get('speed')/1e9)}Gb/s" if i.get('speed') else "-"
            temp = f"{i.get('temperature')}°C" if i.get('temperature') else "-"
            rows.append([i.get('name', 'N/A'), i.get('type', 'N/A'), i.get('status', 'unknown').upper(), str(i.get('index', '-')), speed, temp, i.get('serial') or "-"])
        rows.sort(key=lambda x: natural_sort_key(x[0]))
        smart_print(headers, rows)
    except Exception as e: print(f"❌ Hardware Error: {e}")

def list_hosts(session, base_url):
    try:
        res = session.get(f"{base_url}/hosts")
        log_debug("GET", f"{base_url}/hosts", session.headers, res)
        items = safe_json(res).get('items', [])
        headers = ["HOST_NAME", "IQN"]
        # Removed space in join
        rows = [[h.get('name', 'N/A'), ",".join(h.get('iqns', [])) or "N/A"] for h in items]
        rows.sort(key=lambda x: natural_sort_key(x[0]))
        smart_print(headers, rows)
    except Exception as e: print(f"❌ Host Error: {e}")

def list_volumes(session, base_url):
    try:
        v_res = session.get(f"{base_url}/volumes")
        log_debug("GET", f"{base_url}/volumes", session.headers, v_res)
        c_res = session.get(f"{base_url}/connections")
        log_debug("GET", f"{base_url}/connections", session.headers, c_res)
        
        conns = {}
        for c in safe_json(c_res).get('items', []): 
            conns.setdefault(c.get('volume', {}).get('name'), []).append(c.get('host', {}).get('name'))
        
        headers = ["VOLUME_NAME", "SIZE(GiB)", "CONNECTED_HOSTS"]
        # Removed space in join
        rows = [[v.get('name', 'N/A'), f"{v.get('provisioned', 0)/(1024**3):.1f}", ",".join(conns.get(v.get('name'), ['None']))] for v in safe_json(v_res).get('items', [])]
        rows.sort(key=lambda x: natural_sort_key(x[0]))
        smart_print(headers, rows)
    except Exception as e: print(f"❌ Volume Error: {e}")

def list_subnets(session, base_url):
    try:
        res = session.get(f"{base_url}/subnets")
        log_debug("GET", f"{base_url}/subnets", session.headers, res)
        items = safe_json(res).get('items', [])
        headers = ["SUBNET_NAME", "PREFIX", "VLAN", "MTU", "SERVICES"]
        # Removed space in join
        rows = [[i.get('name', 'N/A'), i.get('prefix', 'N/A'), str(i.get('vlan', '-')), str(i.get('mtu', '-')), ",".join(i.get('services', [])) or "None"] for i in items]
        rows.sort(key=lambda x: natural_sort_key(x[0]))
        smart_print(headers, rows)
    except Exception as e: print(f"❌ Subnet Error: {e}")

def list_nfs(session, base_url):
    try:
        fs_res = session.get(f"{base_url}/file-systems")
        log_debug("GET", f"{base_url}/file-systems", session.headers, fs_res)
        fs_items = safe_json(fs_res).get('items', [])
        
        mem_res = session.get(f"{base_url}/policies/nfs/members")
        log_debug("GET", f"{base_url}/policies/nfs/members", session.headers, mem_res)
        mem_items = safe_json(mem_res).get('items', [])
        
        fs_headers = ["FILE_SYSTEM", "ID", "STATUS"]
        fs_rows = [[f.get('name'), f.get('id'), 'Online' if not f.get('destroyed') else 'Destroyed'] for f in fs_items]
        fs_rows.sort(key=lambda x: natural_sort_key(x[0]))
        smart_print(fs_headers, fs_rows)
        
        exp_headers = ["EXPORT_NAME(PVC)", "POLICY", "ENABLED"]
        exp_rows = [[m.get('export_name', 'N/A'), m.get('policy', {}).get('name', 'N/A'), 'Yes' if m.get('enabled') else 'No'] for m in mem_items if not m.get('destroyed')]
        exp_rows.sort(key=lambda x: natural_sort_key(x[0]))
        smart_print(exp_headers, exp_rows)
    except Exception as e: print(f"❌ NFS List Error: {e}")

# ==========================================
# Networking Functions
# ==========================================

def list_interfaces(session, base_url):
    try:
        res = session.get(f"{base_url}/network-interfaces")
        log_debug("GET", f"{base_url}/network-interfaces", session.headers, res)
        items = safe_json(res).get('items', [])
        
        headers = ["NAME", "TYPE", "ADDRESS", "MASK", "LINK", "SPEED", "SERVICES", "SUBINTERFACES"]
        rows = []
        for i in items:
            eth = i.get('eth', {})
            speed_val = i.get('speed')
            speed = f"{int(speed_val/1e9)}Gb/s" if speed_val else "-"
            link = "UP" if speed_val else "DOWN"
            # Removed space in join
            services = ",".join(i.get('services', [])) or "-"
            subs = ",".join([s.get('name') for s in eth.get('subinterfaces', [])]) or "-"
            rows.append([i.get('name', 'N/A'), eth.get('subtype', 'N/A'), eth.get('address') or "-", eth.get('netmask') or "-", link, speed, services, subs])
        
        rows.sort(key=lambda x: natural_sort_key(x[0]))
        smart_print(headers, rows)
    except Exception as e: print(f"❌ Interface Error: {e}")

def list_interconnections(session, base_url):
    try:
        if_res = session.get(f"{base_url}/network-interfaces")
        log_debug("GET", f"{base_url}/network-interfaces", session.headers, if_res)
        ifaces = safe_json(if_res).get('items', [])
        
        sub_res = session.get(f"{base_url}/subnets")
        log_debug("GET", f"{base_url}/subnets", session.headers, sub_res)
        subnets = safe_json(sub_res).get('items', [])
        
        subnet_dict = {s.get('name'): s for s in subnets}
        
        # Removed space in headers for safer awk parsing
        headers = ["INTERFACE", "TYPE", "LINK", "SPEED", "VLAN", "SUBNET", "IP_ADDRESS", "SERVICES", "PHYSICAL_ANCHORS"]
        rows = []
        
        for i in ifaces:
            name = i.get('name', 'N/A')
            eth = i.get('eth', {})
            subtype = eth.get('subtype', 'unknown')
            
            speed_val = i.get('speed')
            link = "UP" if speed_val else "DOWN"
            # Removed space in speed string (e.g., "25Gb/s" instead of "25 Gb/s")
            speed = f"{int(speed_val/1e9)}Gb/s" if speed_val else "-"
            
            ip = eth.get('address') or "-"
            subnet = eth.get('subnet', {}).get('name') or "-"
            # Removed space in join
            services = ",".join(i.get('services', [])) or "-"
            
            vlan = "-"
            if subnet != "-" and subnet in subnet_dict:
                vlan = str(subnet_dict[subnet].get('vlan', '-'))
            if vlan == "-" and "." in name:
                parts = name.split('.')
                if len(parts) >= 3 and parts[-1].isdigit():
                    vlan = parts[-1]
                    
            anchors = []
            subs = eth.get('subinterfaces', [])
            if subs:
                anchors = [s.get('name') for s in subs]
            
            if not anchors and name.startswith('vir') and name[3:].isdigit():
                port_num = name[3:]
                anchors = [f"ct0.eth{port_num}", f"ct1.eth{port_num}"]
                
            if not anchors and "." in name:
                base = name.split('.')[0]
                anchors = [base]
                
            # Removed space in join
            anchor_str = ",".join(anchors) if anchors else "-"
            
            rows.append([name, subtype, link, speed, vlan, subnet, ip, services, anchor_str])
            
        rows.sort(key=lambda x: natural_sort_key(x[0]))
        smart_print(headers, rows)
        
    except Exception as e: print(f"❌ Interco List Error: {e}")

# ==========================================
# Main Execution
# ==========================================

def main():
    global DEBUG_MODE, UNMASK_TOKENS, GREP_TERM
    parser = argparse.ArgumentParser(description="Pure Storage //X50 R4 Unified Tool (API 2.5 Only)")
    
    parser.add_argument('--arraylist', action='store_true', help='Show array details')
    parser.add_argument('--hardwarelist', action='store_true', help='Show physical component health')
    parser.add_argument('--hostlist', action='store_true', help='Show registered hosts and IQNs')
    parser.add_argument('--volumelist', action='store_true', help='Show volumes and host connections')
    parser.add_argument('--subnetlist', action='store_true', help='Show network subnets')
    parser.add_argument('--interfacelist', action='store_true', help='Show logical network interfaces')
    parser.add_argument('--intercolist', action='store_true', help='Show heavily enriched physical-to-logical interconnections')
    parser.add_argument('--nfslist', action='store_true', help='Show NFS file systems and active exports')
    
    parser.add_argument('--grep', type=str, help='Filter output by term')
    parser.add_argument('--debug', action='store_true', help='Show API requests')
    parser.add_argument('--unmasked-tokens', action='store_true', help='Show API tokens in debug mode')
    
    args = parser.parse_args()
    DEBUG_MODE, UNMASK_TOKENS, GREP_TERM = args.debug, args.unmasked_tokens, args.grep

    if not any([args.arraylist, args.hardwarelist, args.hostlist, args.volumelist, 
                args.subnetlist, args.interfacelist, args.intercolist, args.nfslist]):
        parser.print_help(); sys.exit(0)

    host, token = load_config()

    session, base_url = get_session(host, token)

    if args.arraylist: list_array(session, base_url)
    if args.hardwarelist: list_hardware(session, base_url)
    if args.hostlist: list_hosts(session, base_url)
    if args.volumelist: list_volumes(session, base_url)
    if args.subnetlist: list_subnets(session, base_url)
    if args.nfslist: list_nfs(session, base_url)
    if args.interfacelist: list_interfaces(session, base_url)
    if args.intercolist: list_interconnections(session, base_url)

if __name__ == "__main__":
    main()
