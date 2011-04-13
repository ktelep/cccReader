#!/usr/bin/env python

import dblayer as db_layer
import re
import sys
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound
from xml.etree import ElementTree

# EMC Namespaces
namespace_uri_template = {"CELERRA": "{http://www.emc.com/celerra}%s"}

class cccReader():
    """reads and parses xml file into database structure"""

    sharedDB = None

    def __init__(self,ccc_config_xml=None,is_shared_db=True,db_engine=None,db_debug=False):

        # Setup our shared or non-shared DB connection
        db = None
        if not db_engine:  # We default to in-memory sqlite
            db_engine = "sqlite:///:memory:"

        if is_shared_db == True:
            if not cccReader.sharedDB:
                cccReader.sharedDB = create_engine(db_engine,echo=db_debug)
            db = cccReader.sharedDB
        else:
            db = create_engine(db_engine,echo=db_debug)

        # Run our database create and build our session
        db_layer.Base.metadata.create_all(db)
        Session = sessionmaker(bind=db)
        self.dbconn = Session()

        self.ccc_config_xml=ccc_config_xml
        self.doc_version = None

        try: 
            self.tree = ElementTree.parse(self.ccc_config_xml)
        except IOError:
            print "Unable to read and/or access file %s" % (self.ccc_config_xml)
            exit()

        # Find out if we're using a namespace (CCC v1.3 and below do NOT)
        root=self.tree.getroot()
        print root.attrib
#        self.doc_version = schema_major.text

    def __repr__(self):
        return "cccReader<EMC XML Schema Major: %s Minor %s>" % (self.schema_major_version, self.schema_minor_version)


    def parse(self):
        pass

if __name__ == "__main__":
    nas = cccReader(sys.argv[1])
    nas.parse()
