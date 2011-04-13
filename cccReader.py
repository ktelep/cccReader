#!/usr/bin/env python

import dblayer as db_layer
import re
import sys
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound
from xml.etree import ElementTree

# EMC Namespaces
namespace_uri_template = {"CELERRA": "{http://www.emc.com/celerra}"}

class cccReader():
    """reads and parses xml file into database structure"""

    sharedDB = None

    def _build_path(self,path):
        if self.ns==True:
            path.replace('//','||')
            path.replace('/',namespace_uri_template['CELERRA'])
            path.replace('||','//')
       
        return path

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
        self.ns=False
        self.nas_serial=None

        try: 
            self.tree = ElementTree.parse(self.ccc_config_xml)
        except IOError:
            print "Unable to read and/or access file %s" % (self.ccc_config_xml)
            exit()

        root=self.tree.getroot()

        # Find out if we're using a namespace (CCC v1.3 and below do NOT)
        if '{' in root[0].tag:
            self.ns=True

        # Get the CCC version
        version = self.tree.find(self._build_path('./Version'))

        self.doc_version = version.text
        print self.doc_version

    def __repr__(self):
        return "cccReader<EMC XML Schema Version: %s>" % (self.doc_version)

    def _locate_nas_device(self):
        
        new_nas = db_layer.NAS()
        new_nas.name = self.tree.find(self._build_path('/Celerra/Name')).text
        new_nas.serial_number = self.tree.find(self._build_path('/Celerra/Serial')).text
        new_nas.control_station_1_ip == self.tree.find(self._build_path('/Celerra/Control_Station/IP_Address')).text

        self.dbconn.add(new_nas)
        self.dbconn.commit()
        self.nas_serial = new_nas.serial_number

    def _locate_data_movers(self):
        
        data_movers = self.tree.find(self._build_path('/Celerra/Data_Movers'))
        this_nas = self.dbconn.query(db_layer.NAS).filter(db_layer.NAS.serial_number==self.nas_serial).one()

        for mover in data_movers:
            new_dm = db_layer.Datamover()
            new_dm.name = mover.find(self._build_path('./Name')).text
            new_dm.mover_type = mover.find(self._build_path('./Role')).text
            new_dm.nas = this_nas
            self.dbconn.add(new_dm)

        self.dbconn.commit()


    def _locate_volumes(self):
        
        #Volumes are located in 2 passes, one to populate the DB, the other to create the relationships
        volumes = self.tree.find(self._build_path('/Celerra/Volumes'))

        # Pass 1, just load the table
        vol_children = {}
        id_volname_map = {}   # We have to keep a map of the client_ids fo volumes in this session
        for vol in volumes:
            new_vol = db_layer.Volume()
            new_vol.name = vol.find(self._build_path('./Name')).text
            new_vol.type = vol.find(self._build_path('./Type')).text
            self.dbconn.add(new_vol)
            self.dbconn.commit()

            id_volname_map[new_vol.name] = new_vol.id

            # Store the children for later, so who know who to query
            children = vol.find(self._build_path('./Client_Names'))
            if children is not None:
                vol_children[new_vol.name] = children.text.split()

        # Pass 2, the relation
        for vol in volumes:
            volume_name = vol.find(self._build_path('./Name')).text
            if volume_name in vol_children:
                parent_vol = self.dbconn.query(db_layer.Volume).filter(db_layer.Volume.id==id_volname_map[volume_name]).one()

                for child in vol_children[volume_name]:
                    if child in id_volname_map:  # This protects us from filesystem names that pop up as clients of volumes
                        child_vol = self.dbconn.query(db_layer.Volume).filter(db_layer.Volume.id==id_volname_map[child]).one()
                        child_vol.parents.append(parent_vol)

                self.dbconn.commit()


    def parse(self):
        self._locate_nas_device()
        self._locate_data_movers()
        self._locate_volumes()

if __name__ == "__main__":
    nas = cccReader(sys.argv[1],db_debug=True)
    nas.parse()
