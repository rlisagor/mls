#!/usr/bin/env python

import argparse
import csv
import json
import logging
import os
import re
import sys
import time

from geopy import geocoders
import redis

import zoning


class Processor(object):
    
    def __init__(self, zonedir, geocoder):
        self.zonedir = zonedir
        self.geocoder = geocoder

    def process_mls_dir(self, path):
        results = []
        errors = []
        for mls in os.listdir(path):
            filename = os.path.join(path, mls)
            result, error = self.process_mls_file(mls, filename)
            if error:
                errors.append(error)
            else:
                results.append(result)
            time.sleep(0.5)
        return results, errors

    def process_mls_file(self, mls, filename):
        with open(filename) as fp:
            data = json.loads(fp.read())
            rawaddr = data['address']
            price = int(data['price'].strip('$').replace(',', '')[:-3])
            parts = [p.strip() for p in rawaddr.split(",")]
            addr = ", ".join([parts[0], "Vancouver", "BC"])
            return self.process_listing(mls, addr, price)

    def process_listing(self, mls, addr, price):
        logging.debug("{}: {}".format(mls, addr))
        try:
            info = zoning.lookup_address(self.geocoder, self.zonedir, addr)
            place, (lat, lng), zone = info
        except Exception as e:
            logging.error("!!! Error: {}, {} / {}".format(e, mls, addr))
            return None, (mls, addr)
        else:
            logging.debug("> Address: {}, Zone: {}".format(place, zone))
            result = {'mls': mls, 'address': addr, 'lat': lat, 'lng': lng,
                      'zone': zone, 'price': price, 'place': place}
            return result, None


def write_to_csv(reslults, filename):
    with open(filename, "w") as fp:
        c = csv.DictWriter(fp, ['mls', 'price', 'place', 'zone', 'lat', 'lng'],
                           extrasaction='ignore')
        c.writeheader()
        for result in results:
            c.writerow(result)


def write_to_json(results, filename):
    with open(filename, "w") as fp:
        fp.write(json.dumps(results))


def process_redis(processor, redis_addr, process_all, key="listings"):
    host, port = redis_addr.split(":")
    port = int(port)

    r = redis.StrictRedis(host=host, port=port)
    listings = r.hkeys(key)

    results = []
    errors = []

    for mls in listings:
        data = json.loads(r.hget(key, mls))
        address = data['address'] + ", Vancouver, BC"
        price = data['price']
        if process_all or 'zone' not in data:
            result, error = processor.process_listing(mls, address, price)
            if error:
                errors.append(error)
            else:
                data['zone'] = result['zone']
                data['lat'] = result['lat']
                data['lng'] = result['lng']
                data['place'] = result['place']
                r.hset(key, mls, json.dumps(data))
                results.append(result)
            time.sleep(0.5)
        else:
            results.append(data)

    return results, errors


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Reads a directory of MLS data files, geocodes against "
                    "Google, and outputs a CSV file with addresses, pricing, "
                    "and zoning information")
    ap.add_argument('-k', '--zone-file', default="zoning_districts.kml",
                    help="Zoning KML file")
    ap.add_argument('-r', '--redis', nargs='?', const="localhost:6379",
                    help="Use the given redis server instead of MLS files")
    ap.add_argument('-d', '--dir', help="Directory containing MLS files")
    ap.add_argument('-a', '--all', help="Reprocess even if zone already in DB",
                    action="store_true")
    ap.add_argument('-o', '--outputcsv', help="Filename to write the results")
    args = ap.parse_args()

    if not args.dir and not args.redis:
        ap.error("Must specify -r or -d")

    logging.basicConfig(level=logging.DEBUG, format="%(message)s")

    zonedir = zoning.load_from_kml(args.zone_file)
    geocoder = geocoders.GoogleV3()

    processor = Processor(zonedir, geocoder)

    if args.dir:
        results, errors = processor.process_mls_dir(args.dir)
    else:
        results, errors = process_redis(processor, args.redis, args.all)
    if args.outputcsv:
        write_to_csv(results, args.outputcsv)

    logging.debug(errors)

