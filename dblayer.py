from sqlalchemy import *
from sqlalchemy.orm import mapper,relation,backref
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Frame(Base):
    __tablename__ = 'Frame'

    rid = Column('FrameID', Integer, primary_key=True, autoincrement=True)
    serial_number = Column('SerialNumber', String(25))
    model = Column('Model', String(25))
    spa_ip = Column('SPA', String(100))
    spb_ip = Column('SPB', String(100))
    cache_hwm = Column('CacheHWM', Integer)
    cache_lwm = Column('CacheLWM', Integer)
    wwn = Column('WWN', String(255))

    def __init__(self):
        pass

    def __repr__(self):
        repr_items = [self.serial_number, self.model, self.spa_ip, self.spb_ip]
        repr_string = "', '".join(tuple(map(str, repr_items)))
        return "Frame<'%s'>" % repr_string

class LUN(Base):
    __tablename__ = 'LUNS'

    wwn = Column('WWN', String(50), primary_key=True)
    alu = Column('ALU', Integer)
    name = Column('Name', String(50))
    state = Column('State', String(50))
    capacity = Column('Capacity', BigInteger)
    current_owner = Column('Ownership', String(5))
    default_owner = Column('DefaultOwner', String(5))
    is_read_cache_enabled = Column('ReadCacheEnabled', SMALLINT)
    is_write_cache_enabled = Column('WriteCacheEnabled', SMALLINT)
    is_meta_head = Column('isMetaHead', SMALLINT)
    is_meta_member = Column('isMetaMember', SMALLINT)
    meta_head = Column('MetaHead', String(50))
    raidgroup_id = Column('RaidID', Integer)
    storage_group_wwn = Column('StorageGroup', Integer)
    hlu = Column('HLU', Integer)


    def __init__(self):
        pass

    def __repr__(self):
        return "LUN<'%s','%s','%s','%s'>" % (
                self.wwn, str(self.alu), self.name, str(self.capacity))


class NAS(Base):
    """ NAS base class """
    __tablename__  = 'NAS'
    serial_number = Column('SerialNumber', String(25), primary_key=True, nullable=False)
    control_station_1_ip = Column('CS01IP', String(25))
    control_station_2_ip = Column('CS02IP', String(25))

class Datamover(Base):
    """ Datamover object """
    __tablename__ = 'DataMover'
    
    mover_id = Column('rid', Integer, primary_key = True, nullable=False, autoincrement=True)
    name = Column('Name', String(25), nullable=False)
    mover_type = Column('Type', String(1))
    serial_number = Column('NASSerialNumber', String(25), ForeignKey('NAS.SerialNumber'))
    nas = relation('NAS', backref='datamovers')
    
class NASDisk(Base):
    """ Disk Object """
    __tablename__ = "NasDisk"
    
    id = Column('ID', Integer, primary_key=True, nullable=False)
    in_use = Column('InUse', SMALLINT, nullable=False)
    size = Column('size', BigInteger, nullable=False)
    lun_wwn_id = Column('WWN', String(50), ForeignKey('LUNS.WWN'))
    lun = relation('LUN', backref='nas_luns')
    type = Column('Type',String(25))
    volumeid = Column('VolumeID', Integer, ForeignKey('Volumes.ID'))
    volume = relation('Volumes', backref='disk')
    serial_number = Column('NASSerialNumber', String(25), ForeignKey('NAS.SerialNumber'))
    nas = relation('NAS', backref='disks')
    
# Buildout our Many-to-Many relationship within the Volumes table    
VolumeRelationship = Table(
    'VolumeRelationship', Base.metadata,
    Column('ParentID', Integer, ForeignKey('Volumes.ID')),
    Column('VolumeID', Integer, ForeignKey('Volumes.ID'))
    )

class Volume(Base):
    """ Volume Object """
    __tablename__ = "Volumes"
    
    id = Column('ID', Integer, primary_key=True, nullable=False)
    type = Column('Type', String(25))
    name = Column('Name', String(25))
    poolid = Column('pool', Integer, ForeignKey('Pools.ID'))
    parents = relation(
                    'Volume',secondary=VolumeRelationship,
                    primaryjoin=VolumeRelationship.c.VolumeID==id,
                    secondaryjoin=VolumeRelationship.c.ParentID==id,
                    backref="children")


ClientPoolRelationship = Table(
    'ClientPools', Base.metadata,
    Column('PoolID', Integer, ForeignKey('Pools.ID')),
    Column('VolumeID', Integer, ForeignKey('Volumes.ID'))
    )
    
class Pool(Base):
    """ Pool Object """
    __tablename__ = "Pools"
    
    id = Column('ID', Integer, primary_key=True, nullable=False)
    name = Column('Name', String(40), nullable=False)
    description = Column('Description', String(40), nullable=False)
    in_use = Column('InUse', SMALLINT, nullable=False)
    profile = Column('VolumeProfile', String(10), nullable=False)
    
class Client(Base):
    """ Client Filesystems """
    __tablename__ = 'Client'
    
    client_id = Column('ClientID', Integer, primary_key=True, nullable=False)
    name = Column('name', String(50), nullable=False)
    vpfs_id = Column('VPFSID', String(50))
    type = Column('Type',String(25))
    ro_host_id = Column('ROHostID', String(60), ForeignKey('DataMover.rid'))
    rw_host_id = Column('RWHostID', String(60), ForeignKey('DataMover.rid'))
    rw_host = relation('Datamover',backref="rw_clients")
    ro_host = relation('Datamover',backref="ro_clients")
    parent_client_id = Column('ParentClientID',Integer,ForeignKey('Client.ClientID'))
    parent = relation('Client', backref='children')
    total_size = Column('totalSize', BigInteger)
    free_size = Column('FreeSize', BigInteger)
    used_size = Column('UsedSize', BigInteger)
    volume_id = Column('VolumeID', Integer, ForeignKey('Volumes.ID'))
    volume = relation('Volume', backref='clients')
    pools = relation('Pool', secondary=ClientPoolRelationship, backref='clients')

class CIFSserver(Base):
    """ CIFS server object """
    __tablename__ = 'CifsServers'
    
    name = Column('Name', String(30), nullable=False, primary_key=True)
    ip = Column('IP', String(15))
    domain = Column('Domain', String(40))
    datamover_id = Column('DatamoverID', ForeignKey('DataMover.rid'))
    datamover = relation('Datamover', backref='cifs_servers')
    
class Export(Base):
    """ Export Object """
    __tablename__ = 'Export'
    cifs_server_id = Column('CifsServerName', String(30), nullable=False, primary_key=True)
    cifs_server = relation('CIFServer', backref='exports')
    share_name = Column('ShareName', String(100), nullable=False, primary_key=True)
    share_path = Column('ClientShare', String(100), nullable=False)
    client_id = Column('ClientID', Integer, ForeignKey('Client.ClientID'))
    client = relation('Client', backref='exports')
