"""
Looks for MLS listings to be parsed, and adds them to a list for fetcher.py to grab
"""
import sys
import boto
import time
import logging
from logging.handlers import SysLogHandler
import aws

from lib import realtylink

log = logging.getLogger("searcher")

sdb = boto.connect_sdb()
sqs = boto.connect_sqs()

mls_domain = sdb.get_domain("mls")
mls_queue = sqs.get_queue("mls_fetcher")

test_results = [('V847348', '$788,000.00'), ('V845315', '$749,000.00'), ('V831476', '$799,000.00'), ('V835285', '$658,000.00'), ('V842022', '$658,000.00'), ('V854413', '$838,000.00'), ('V851993', '$850,000.00'), ('V839052', '$838,000.00'), ('V850019', '$849,000.00'), ('V842451', '$879,000.00'), ('V854759', '$938,000.00'), ('V837202', '$1,038,000.00'), ('V826859', '$998,000.00'), ('V843154', '$998,000.00'), ('V843917', '$998,000.00'), ('V845055', '$1,199,000.00'), ('V852994', '$1,199,000.00'), ('V818446', '$1,129,000.00'), ('V826098', '$1,098,000.00'), ('V838474', '$1,168,000.00'), ('V810654', '$1,299,000.00'), ('V842408', '$1,288,000.00'), ('V843628', '$1,268,000.00'), ('V829481', '$1,227,000.00'), ('V853976', '$1,199,000.00'), ('V837986', '$1,488,000.00'), ('V834877', '$1,690,000.00'), ('V838126', '$1,399,000.00'), ('V835566', '$1,590,000.00'), ('V836286', '$1,758,900.00'), ('V842776', '$1,850,000.00'), ('V843946', '$2,880,000.00'), ('V855651', '$2,398,000.00')]

def pad_price(normalized):
    padded = "0" * (8-len(normalized)) + normalized
    return padded
    
def needs_update(mls, price):
    log.info("Looking for %s for %s" % (price, mls))
    rs = mls_domain.select("SELECT * FROM mls WHERE mls='%s'" % mls)
    for item in rs:
        for existing_price, timestamp in aws.get_price_list(item["prices"]):
            # If there is an item with the same price, this item doesn't need an update
            if existing_price == price:
                log.info("Found it")
                return False, item
    return True, None

def main(argv):
    add_count = 0
    
    for city_name, city_id in realtylink.cities.items():
        for region in realtylink.regions[city_name]:
            for property_type in (realtylink.TOWNHOUSE, realtylink.APARTMENT, realtylink.HOUSE):
        # for region in (22,):
        #     for property_type in (2,):        
                log.info("Searching %s - %s for %s" % (city_name, region, property_type))
                
                results = realtylink.search(property_type=property_type, 
                                  city=city_id, 
                                  areas=[region])
                for mls, price in results:
                    normalized_price = pad_price(realtylink.fix_price(price))
                    update, result = needs_update(mls, price)
                    if update:
                        log.info("Queuing %s" % mls)
                        m = mls_queue.new_message(mls)
                        mls_queue.write(m)
                        add_count += 1
                    else:
                        result["last_seen"] = aws.get_iso_timestamp()
                        if "first_seen" not in result:
                            result["first_seen"] = aws.get_iso_timestamp()
                        result.save()
                time.sleep(15)
    
    log.info("Added %s entries to the parse queue" % add_count)

if __name__=="__main__":
    logging.basicConfig()
    if sys.platform == "darwin":
            # Apple made 10.5 more secure by disabling network syslog:
            address = "/var/run/syslog"
    else:
            address = ('localhost', 514)
    syslog = SysLogHandler(address)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)-19s %(levelname)-7s - %(message)s"))
    formatter = logging.Formatter('%(name)s: %(levelname)s %(message)s')
    syslog.setFormatter(formatter)
    syslog.setLevel(logging.INFO)
    logging.getLogger().addHandler(syslog)    
    logging.getLogger().setLevel(logging.INFO)
    
    sys.exit(main(sys.argv))
