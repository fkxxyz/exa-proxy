#!/usr/bin/env python3
"""Exa Proxy CLI 管理工具"""

import sys
import json
import argparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE_URL = "http://127.0.0.1:8080"

def make_request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if data:
        data = json.dumps(data).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req) as response:
            if response.status == 204:
                return None
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        print(f"Error: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)

def cmd_list(args):
    keys = make_request("GET", "/api/keys")
    if not keys:
        print("No keys found.")
        return
    print(f"{'ID':<38} {'Name':<20} {'Enabled':<8} {'Requests':<10} {'Success':<8} {'429':<6} {'5xx':<6}")
    print("-" * 110)
    for key in keys:
        stats = key["stats"]
        print(f"{key['id']:<38} {key['name']:<20} {'Yes' if key['enabled'] else 'No':<8} {stats['total_requests']:<10} {stats['success_count']:<8} {stats['error_429_count']:<6} {stats['error_5xx_count']:<6}")

def cmd_add(args):
    data = {"key": args.key}
    if args.name:
        data["name"] = args.name
    result = make_request("POST", "/api/keys", data)
    print(f"Added key: {result['id']}")
    print(f"Name: {result['name']}")

def cmd_stats(args):
    stats = make_request("GET", "/api/keys/stats")
    print(json.dumps(stats, indent=2))

def cmd_health(args):
    health = make_request("GET", "/health")
    print(f"Status: {health['status']}")
    print(f"Available keys: {health['available_keys']}/{health['total_keys']}")

def main():
    parser = argparse.ArgumentParser(description="Exa Proxy CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("list", help="List all keys")
    add_parser = subparsers.add_parser("add", help="Add new key")
    add_parser.add_argument("key", help="Exa API key")
    add_parser.add_argument("--name", help="Friendly name")
    subparsers.add_parser("stats", help="Show statistics")
    subparsers.add_parser("health", help="Health check")
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    commands = {"list": cmd_list, "add": cmd_add, "stats": cmd_stats, "health": cmd_health}
    commands[args.command](args)

if __name__ == "__main__":
    main()
