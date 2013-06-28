#!/usr/bin/env python

import argparse
import sys

from collections import defaultdict
from geopy import geocoders
from lxml import etree
from shapely.geometry import Polygon, Point


class ZoneDirectory(object):

    def __init__(self, zones):
        self.zones = zones

    def lookup(self, lt, ln):
        for zone, polygons in self.zones.iteritems():
            for polygon in polygons:
                if polygon.contains(Point(ln, lt)):
                    return zone


def load_from_kml(filename):

    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    xp = "kml:Document/kml:Folder[@id='kml_ft_Zoning_Districts']/kml:Placemark"

    def get_boundary(polygon, kind):
        bndry_xp = "kml:{}BoundaryIs/kml:LinearRing/kml:coordinates".format(kind)
        coord_els = polygon.findall(bndry_xp, namespaces=ns)

        result = []
        for coord_el in coord_els:
            coordinates = coord_el.text.strip()
            # coordinates are "lat,long,alt lat,long,alt, ..."
            c = [tuple(float(x) for x in pair.split(",")[:2])
                 for pair in coordinates.split(" ")]
            result.append(c)
        return result

    zones = defaultdict(list)

    with open(filename) as fp:
        doc = etree.parse(fp).getroot()

    for placemark in doc.xpath(xp, namespaces=ns):
        name_xp = "kml:ExtendedData//kml:SimpleData[@name='zone_name']"
        zone_name = placemark.findtext(name_xp, namespaces=ns)
        for polygon in placemark.findall("kml:Polygon", namespaces=ns):
            outer_bndries = get_boundary(polygon, "outer")
            inner_bndries = get_boundary(polygon, "inner")
            assert len(outer_bndries) == 1

            p = Polygon(outer_bndries[0], inner_bndries)
            zones[zone_name].append(p)

    return ZoneDirectory(zones)


def lookup_address(geocoder, zonedir, address):
    try:
        results = geocoder.geocode(address, exactly_one=False)
        place, (lat, lng) = results[0]
    except ValueError:
        return None, None, None
    zone = zonedir.lookup(lat, lng)
    return place, (lat, lng), zone


if __name__ == "__main__":
    epilog = """Use the following commands to obtain zoning file:

wget http://data.vancouver.ca/download/kml/zoning_districts.kmz
unzip zoning_districts.kmz zoning_districts.kml
"""
    ap = argparse.ArgumentParser(description="Looks up Vancouver zone codes "
                                             "for an address",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=epilog)
    ap.add_argument('-f', '--kml', default="zoning_districts.kml",
                    metavar="FILENAME", help="use the given KML filename")
    ap.add_argument('address', help="address to look up")
    args = ap.parse_args()

    print "Parsing KML file"
    zonedir = load_from_kml(args.kml)

    print "Geocoding"
    g = geocoders.GoogleV3()
    place, _, zone = lookup_address(g, zonedir, args.address)
    print "Found:", place
    print "Zone: ", zone
    if not zone:
        exit(1)
