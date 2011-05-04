from sqlalchemy import *
from sqlalchemy.orm import mapper,relation,backref
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Frame(Base):
    __tablename__ = 'Frame'

    rid = Column('FrameID', Integer, primary_key=True, autoincrement=True)
    serial_number = Column('SerialNumber', String(25))

class RAIDGroup(Base):
    __tablename__ = 'RAIDGroup'

    rid = Column('RaidID', Integer, primary_key=True, autoincrement=True)
    group_number = Column('RaidGroupID', Integer)
    luns = relation('LUN', backref='raid_group')

class Drive(Base):
    __tablename__ = 'Drive'

    rid = Column('DriveID', Integer, primary_key=True, autoincrement=True)
    location = Column('Location', String(25))
    raidgroup_id = Column('RaidID', Integer, ForeignKey('RAIDGroup.RaidID'))
    frame_id = Column('FrameID', Integer, ForeignKey('Frame.FrameID'))
    raidgroup = relation('RAIDGroup', backref='drives')
    frame = relation('Frame', backref='drives')


class LUN(Base):
    __tablename__ = 'LUNS'

    wwn = Column('WWN', String(50), primary_key=True)
    alu = Column('ALU', Integer)
    raidgroup_id = Column('RaidID', Integer, ForeignKey('RAIDGroup.RaidID'))

class NAS(Base):
    """ NAS base class """
    __tablename__  = 'NAS'
    name = Column('Name', String(25), nullable=False)

    serial_number = Column('SerialNumber', String(25), primary_key=True, nullable=False)
    control_station_1_ip = Column('CS01IP', String(25))
    control_station_2_ip = Column('CS02IP', String(25))


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
    volume = relation('Volume', backref='disk')
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
    poolid = Column('PoolID', Integer, ForeignKey('Pools.ID'))
    parents = relation(
                    'Volume',secondary=VolumeRelationship,
                    primaryjoin=VolumeRelationship.c.VolumeID==id,
                    secondaryjoin=VolumeRelationship.c.ParentID==id,
                    backref="children")


ClientPoolRelationship = Table(
    'ClientPools', Base.metadata,
    Column('PoolID', Integer, ForeignKey('Pools.ID')),
    Column('ClientID', Integer, ForeignKey('Client.ClientID'))
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
    ro_host_id = Column('RODMID', String(60), ForeignKey('DataMover.DataMoverID'))
    rw_host_id = Column('RWDMID', String(60), ForeignKey('DataMover.DataMoverID'))
    parent_client_id = Column('ParentClientID',Integer,ForeignKey('Client.ClientID'))
    parent = relation('Client', backref=backref('children', remote_side="Client.client_id"))
    total_size = Column('totalSize', BigInteger)
    free_size = Column('FreeSize', BigInteger)
    used_size = Column('UsedSize', BigInteger)
    volume_id = Column('VolumeID', Integer, ForeignKey('Volumes.ID'))
    volume = relation('Volume', backref='clients')
    pools = relation('Pool', secondary=ClientPoolRelationship, backref='clients')

class Datamover(Base):
    """ Datamover object """
    __tablename__ = 'DataMover'
    
    mover_id = Column('DataMoverID', Integer, primary_key = True, nullable=False, autoincrement=True)
    name = Column('Name', String(25), nullable=False)
    mover_type = Column('Type', String(10))
    serial_number = Column('NASSerialNumber', String(25), ForeignKey('NAS.SerialNumber'), nullable=False)
    nas = relation('NAS', backref='datamovers')
    ro_clients = relation('Client',primaryjoin=Client.ro_host_id==mover_id,backref="ro_host")
    rw_clients = relation('Client',primaryjoin=Client.rw_host_id==mover_id,backref="rw_host")
    
class CIFSserver(Base):
    """ CIFS server object """
    __tablename__ = 'CifsServers'
    
    name = Column('Name', String(30), nullable=False, primary_key=True)
    ip = Column('IP', String(15))
    domain = Column('Domain', String(40))
    datamover_id = Column('DatamoverID', ForeignKey('DataMover.DataMoverID'))
    datamover = relation('Datamover', backref='cifs_servers')
    
class Export(Base):
    """ Export Object """
    __tablename__ = 'Export'
    cifs_server_id = Column('CifsServerName', String(30), ForeignKey('CifsServers.Name'))
    cifs_server = relation('CIFSserver', backref='exports')
    share_id = Column('ExportID', Integer, autoincrement=True, primary_key=True)
    share_name = Column('ShareName', String(100), nullable=False)
    share_path = Column('ClientShare', String(100), nullable=False)
    client_id = Column('ClientID', Integer, ForeignKey('Client.ClientID'))
    client = relation('Client', backref='exports')
    
