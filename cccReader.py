#!/usr/bin/env python26

import dblayer as db_layer
import re
import sys
import os
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound
from xml.etree import ElementTree

# EMC Namespaces
namespace_uri_template = {"CELERRA": "{http://www.emc.com/celerra}"}
size_multiplier = {"KB": 1024,
                   "MB": 1024*1024,
                   "GB": 1024*1024*1024,
                   "TB": 1024*1024*1024*1024 }

class cccReader():
    """reads and parses xml file into database structure"""

    sharedDB = None

    def _build_path(self,path):
        if self.ns==True:
            tstring = path.replace('//','||')
            tstring = tstring.replace('/','/'+namespace_uri_template['CELERRA'])
            tstring = tstring.replace('||','//')
        return tstring

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
        self.pool_map={}
        self.mover_map={}
        self.fs_map={}
        self.mountpoints={}
        self.id_volname_map={}

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
            self.mover_map[new_dm.name] = new_dm.mover_id

            ifconfig = {}
            # Get an interface to IP address mapping
            interfaces = mover.findall(self._build_path('./Network/Interface'))
            if interfaces:
                for iface in interfaces:
                    name = iface.find(self._build_path('./Name')).text
                    ip = iface.find(self._build_path('./IP')).text
                    ifconfig[name] = ip

            # Find our CIFS servers also
            cifs_servers = mover.findall(self._build_path('./CIFS/Server'))
            if cifs_servers:
                for server in cifs_servers:
                    new_cifs = db_layer.CIFSserver()

                    new_cifs.name = server.find(self._build_path('./Name')).text
                    new_cifs.domain =  server.find(self._build_path('./Domain')).text
                    iface = server.find(self._build_path('./Interface'))
                    if iface is not None:
                        new_cifs.ip = ifconfig[iface.text]

                    new_cifs.datamover = new_dm
                    self.dbconn.add(new_cifs)

        self.dbconn.commit()


    def _locate_volumes(self):
        
        #Volumes are located in 2 passes, one to populate the DB, the other to create the relationships
        volumes = self.tree.find(self._build_path('/Celerra/Volumes'))

        # Pass 1, just load the table
        vol_children = {}
        for vol in volumes:
            new_vol = db_layer.Volume()
            new_vol.name = vol.find(self._build_path('./Name')).text
            new_vol.type = vol.find(self._build_path('./Type')).text

            pool = vol.findtext(self._build_path('./Storage_Pool_Name'))
            if pool is not None:
                #This is a pool member, so we must add it as such
                new_vol.poolid = self.pool_map[pool]

            self.dbconn.add(new_vol)
            self.dbconn.commit()

               
            self.id_volname_map[new_vol.name] = new_vol.id

            # Store the children for later, so who know who to query
            children = vol.find(self._build_path('./Client_Names'))
            if children is not None:
                vol_children[new_vol.name] = children.text.split()

        # Pass 2, the relation
        for vol in volumes:
            volume_name = vol.find(self._build_path('./Name')).text
            if volume_name in vol_children:
                parent_vol = self.dbconn.query(db_layer.Volume).filter(db_layer.Volume.id==self.id_volname_map[volume_name]).one()

                for child in vol_children[volume_name]:
                    if child in self.id_volname_map:  # This protects us from filesystem names that pop up as clients of volumes
                        child_vol = self.dbconn.query(db_layer.Volume).filter(db_layer.Volume.id==self.id_volname_map[child]).one()
                        child_vol.parents.append(parent_vol)
                #TODO: we could use an else here to grab the filesystems for pool info later?

                self.dbconn.commit()

    def _locate_pools(self):

        pools = self.tree.find(self._build_path('/Celerra/Storage_Pools'))

        for pool in pools:
            new_pool = db_layer.Pool()
            new_pool.name = pool.find(self._build_path('./Name')).text
            new_pool.description = pool.findtext(self._build_path('./Description'), default="")
            new_pool.profile = pool.find(self._build_path('./Disk_Type')).text
           
            # Calculate the capacity, if they match it's unused (either 0 with no disk or no clients)
            tot_cap = pool.find(self._build_path('./Total_Capacity')).text
            used_cap = pool.find(self._build_path('./Used_Capacity')).text
            if tot_cap == used_cap:
                new_pool.in_use = 0
            else:
                new_pool.in_use = 1

            self.dbconn.add(new_pool)
            self.dbconn.commit()

            # Store the poolID for later volume tracking
            self.pool_map[new_pool.name] = new_pool.id

    def _locate_client_filesystems(self):

        # First we need all the mountpoints
        mounts = {}
        datamovers = self.tree.find(self._build_path('/Celerra/Data_Movers'))
        for mover in datamovers:
            mover_name = mover.findtext(self._build_path('./Name'))
            mount_points = mover.find(self._build_path('./Mounts'))
            if mount_points is not None:
                for fs_mount in mount_points:
                    fs_name = fs_mount.findtext(self._build_path('./File_System'))
                    fs_type = fs_mount.findtext(self._build_path('./Type'))
                    fs_mp = fs_mount.findtext(self._build_path('./Path'))

                    mounts[fs_name] = (fs_type, mover_name, fs_mp)

        # Hunt down our filesystems
        file_systems = self.tree.find(self._build_path('/Celerra/File_Systems'))

        for fs in file_systems:
            client = db_layer.Client()
            client.name = fs.findtext(self._build_path('./Name'))
            client.type = fs.findtext(self._build_path('./Type'))

            if client.type == 'avm_group': continue   # These are actually pools

            client.total_size = int(fs.findtext(self._build_path('./Size_Allocated')))
            client.used_size = int(fs.findtext(self._build_path('./Size_Used')))
            client.free_size = client.total_size - client.used_size
            client.volume_id = self.id_volname_map[fs.findtext(self._build_path('./Volume_Name'))]

            self.dbconn.add(client)

            # Determine mounts
            if client.name in mounts:
                if (mounts[client.name][0] == 'ro'):
                    client.ro_host_id = self.mover_map[mounts[client.name][1]]
                elif (mounts[client.name][0] == 'rw'):
                    client.rw_host_id = self.mover_map[mounts[client.name][1]]

                # Track our mountpoints into the FS
                self.mountpoints[mounts[client.name][2]] = client.name

            self.dbconn.commit()
            self.fs_map[client.name] = client.client_id

            # Pool hunt by volumes, this is slightly recursive and time consuming, but
            # is the only real way to confirm you get the right pools for the volumes
            volume_list = []
            volume_list.append(client.volume_id)

            while len(volume_list) > 0:
                vol_id = volume_list.pop()
                vol = self.dbconn.query(db_layer.Volume).filter(db_layer.Volume.id==vol_id).one()
                if 'root_' in vol.name: 
                    continue  # This is a root disk, so it's not in a pool 

                if vol.poolid == None:
                    for parent in vol.parents:
                        volume_list.append(parent.id)
                else:
                    pool = self.dbconn.query(db_layer.Pool).filter(db_layer.Pool.id==vol.poolid).one()
                    client.pools.append(pool)


        # Second pass to assign parent/child relationships to checkpoints
        for fs in file_systems:
            fs_name = fs.findtext(self._build_path('./Name'))
            fs_type = fs.findtext(self._build_path('./Type'))

            if fs_type=='ckpt':
                parent_name = fs.findtext(self._build_path('./Backup_Of'))
                checkpoint_row = self.dbconn.query(db_layer.Client).filter(db_layer.Client.client_id==self.fs_map[fs_name]).one()
                parent_row = self.dbconn.query(db_layer.Client).filter(db_layer.Client.client_id==self.fs_map[parent_name]).one()
                checkpoint_row.parent.append(parent_row)
            
        self.dbconn.commit()

    def _locate_exports(self):
        datamovers = self.tree.find(self._build_path('/Celerra/Data_Movers'))
        for mover in datamovers:
            shares = mover.findall(self._build_path('./CIFS/Share'))
            if shares is not None:
                for share in shares:
                    cifs_servers = share.findtext(self._build_path('./Servers')).split()
                    for server in cifs_servers:
                        new_export = db_layer.Export()
                        new_export.share_name = share.findtext(self._build_path('./Name'))
                        new_export.share_path = share.findtext(self._build_path('./Path_Standard'))
                        new_export.cifs_server_id = server
 

                        # Now we hunt down the actual FS (See Stack Overflow 4453602)
                        temp_path = new_export.share_path
                        while temp_path not in self.mountpoints and temp_path != '/':
                            temp_path = os.path.dirname(temp_path)

                        new_export.client_id = self.fs_map[self.mountpoints[temp_path]]

                        self.dbconn.add(new_export)
                    self.dbconn.commit()

 
    def _locate_nas_disk(self):
        disks = self.tree.findall(self._build_path('/Celerra/Disks/Disk'))
        for disk in disks:
            new_disk = db_layer.NASDisk()

            name = disk.findtext(self._build_path('./Name'))
            new_disk.volumeid = self.id_volname_map[name]
            new_disk.type = disk.findtext(self._build_path('./Type'))

            in_use = disk.findtext(self._build_path('./In_Use'))
            if in_use == 'y':
                new_disk.in_use = 1
            else:
                new_disk.in_use = 0

            size = int(disk.findtext(self._build_path('./Size')))
            size_qual = disk.findtext(self._build_path('./Size_Qualifier'))
            new_disk.size = size * size_multiplier[size_qual]
            new_disk.serial_number = self.nas_serial

            # Find our frame and ALU
            storage_frame = disk.findtext(self._build_path('./Storage_ID'))
            storage_dev = disk.findtext(self._build_path('./Storage_Device'))
            storage_dev = int(storage_dev, 16)  # Convert from Hex String to Integer in one swoop

            # Check for a LUNs table, if we dont' have it, then we don't create the 'LUN' relations
            query = self.dbconn.query(db_layer.LUN).filter(db_layer.Frame.serial_number==storage_frame).\
                            join(db_layer.RAIDGroup).\
                            join(db_layer.Drive).\
                            join(db_layer.Frame).\
                            filter(db_layer.LUN.alu==storage_dev).one()
            new_disk.lun_wwn_id = query.wwn
            self.dbconn.add(new_disk)
            self.dbconn.commit()

    def parse(self):
        self._locate_nas_device()
        self._locate_pools()
        self._locate_volumes()
        self._locate_data_movers()
        self._locate_client_filesystems()
        self._locate_exports()
        self._locate_nas_disk()

if __name__ == "__main__":
    nas = cccReader(sys.argv[1],db_engine='sqlite:////tmp/slough.db', db_debug=False)
    #nas = cccReader(sys.argv[1],db_engine='mssql+pymssql://zzstorage:Kur71zth3M%40n@ann330db01.ftitools.com/storage_staging', db_debug=True)

    nas.parse()
