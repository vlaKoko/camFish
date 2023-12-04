import os
import re
import sys
import errno
from subprocess import Popen,PIPE

def find_device(data, pciid):
    id = re.escape(pciid)
    m = re.search("^" + id + "\s(.*)$", data, re.MULTILINE)
    return m.group(1)

def pretty_size(size):
    size_strs = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
    last_size = size
    fract_size = size
    num_divs = 0

    while size > 1:
        fract_size = last_size
        last_size = size
        size /= 1024
        num_divs += 1

    num_divs -= 1
    fraction = fract_size / 1024
    pretty = "%.2f" % fraction
    pretty = pretty + size_strs[num_divs]
    return pretty

def virtual_device(path):
    for dir in os.listdir(path):
        if re.search("device", dir):
            return 0
    return 1

class Device:
    def __init__(self):
        self.sectorsize = ""
        self.sectors = ""
        self.rotational = ""
        self.sysdir = ""
        self.host = ""
        self.model = ""
        self.vendor = ""
        self.holders = []
        self.diskname = ""
        self.partitions = []
        self.uuids = []
        self.removable = ""
        self.start = ""
        self.discard = ""
        self.sysfs_no_links = 0

    def populate_model(self):
        try:
            f = open(self.sysdir + "/device/model")
            self.model = f.read().rstrip()
            f.close()
        except IOError:
            # do nothing
            pass

    def populate_vendor(self):
        try:
            f = open(self.sysdir + "/device/vendor")
            self.vendor = f.read().rstrip()
            f.close()
        except IOError:
            #do nothing
            pass

    def populate_sectors(self):
        try:
            f = open(self.sysdir + "/size")
            self.sectors = f.read().rstrip()
            f.close()
        except IOError:
            self.sectors = 0

    def populate_sector_size(self):
        try:
            f = open(self.sysdir + "/queue/hw_sector_size")
            self.sectorsize = f.read().rstrip()
            f.close()
        except IOError:
            # if this sysfs doesnt show us sectorsize then just assume 512
            self.sectorsize = "512"

    def populate_rotational(self):
        try:
            f = open(self.sysdir + "/queue/rotational")
            rotation = f.read().rstrip()
            f.close()
        except IOError:
            self.rotational = "Could not determine rotational"
            return
        if rotation == "1":
            self.rotational = "Spinning disk"
        else:
            self.rotational = "SSD"

    def populate_host(self, pcidata):
        if self.sysfs_no_links == 1:
            try:
                sysdir = os.readlink(os.path.join(self.sysdir, "device"))
            except:
                pass
        else:
            sysdir = self.sysdir
        m = re.match(".+/\d+:(\w+:\w+\.\w)/host\d+/\s*", sysdir)
        if m:
            pciid = m.group(1)
            self.host = find_device(pcidata, pciid)
        else:
            self.host = ""

    def populate_diskname(self):
        m = re.match(".*/(.+)$", self.sysdir)
        self.diskname = m.group(1)

    def populate_holders(self):
        for dir in os.listdir(self.sysdir + "/holders"):
            if re.search("^dm-.*", dir):
                try:
                    f = open(self.sysdir + "/holders/" + dir + "/dm/name")
                    name = f.read().rstrip()
                    f.close()
                    self.holders.append(name)
                except IOError:
                    self.holders.append(dir)
            else:
                self.holders.append(dir)

    def populate_discard(self):
        try:
            f = open(self.sysdir + "/queue/discard_granularity")
            discard = f.read().rstrip()
            f.close()
            if discard == "0":
                self.discard = "No"
            else:
                self.discard = "Yes"
        except IOError:
            self.discard = "No"

    def populate_start(self):
        try:
            f = open(self.sysdir + "/start")
            self.start = f.read().rstrip()
            f.close()
        except IOError:
            pass

    def populate_partitions(self):
        for dir in os.listdir(self.sysdir):
            m = re.search("(" + self.diskname + "\w+)", dir)
            if m:
                partname = m.group(1)
                part = Device()
                part.sysdir = self.sysdir + "/" + partname
                part.populate_part_info()
                self.partitions.append(part)
                p = Popen(["blkid", "/dev/{}".format(part.diskname)], stdout = PIPE)
                uuid_data = p.stdout.read().decode(errors = 'ignore')
                uuid = re.compile('(?<=UUID=").*?(?=")', re.IGNORECASE).findall(uuid_data)[0]
                self.uuids.append(uuid)

    def populate_part_info(self):
        """ Only call this if we are a partition """
        self.populate_diskname()
        self.populate_holders()
        self.populate_sectors()
        self.populate_start()

    def populate_removable(self):
        try:
            f = open(self.sysdir + "/removable")
            remove = f.read().rstrip()
            f.close()
            if remove == "1":
                self.removable = "Yes"
            else:
                self.removable = "No"
        except IOError:
            self.removable = "No"

    def populate_all(self, pcidata):
        self.populate_diskname()
        self.populate_holders()
        self.populate_partitions()
        self.populate_removable()
        self.populate_model()
        self.populate_vendor()
        self.populate_sectors()
        self.populate_sector_size()
        self.populate_rotational()
        self.populate_discard()
        self.populate_host(pcidata)

def GatherDevices():
    p = Popen(["lspci"], stdout=PIPE)
    err = p.wait()
    if err:
        print("Error running lspci")
        sys.exit()
    pcidata = p.stdout.read()

    sysfs_no_links = 0
    devices = []

    if len(sys.argv) > 1:
        m = re.match("/dev/(\D+)\d*", sys.argv[1])
        if m:
            block = m.group(1)
        else:
            block = sys.argv[1]

        try:
            path = os.readlink(os.path.join("/sys/block/", block))
        except OSError as e:
            if e.errno == errno.EINVAL:
                path = block
            else:
                print("Invalid device name " + block)
                sys.exit()
        d = Device()
        d.sysdir = os.path.join("/sys/block", path)
        d.populate_all(pcidata)
        devices.append(d)
    else:
        for block in os.listdir("/sys/block"):
            try:
                if sysfs_no_links == 0:
                    path = os.readlink(os.path.join("/sys/block/", block))
                else:
                    path = block
            except OSError as e:
                if e.errno == errno.EINVAL:
                    path = block
                    sysfs_no_links = 1
                else:
                    continue
            if re.search("virtual", path):
                continue
            if sysfs_no_links == 1:
                sysdir = os.path.join("/sys/block", path)
                if virtual_device(sysdir) == 1:
                    continue
            d = Device()
            d.sysdir = os.path.join("/sys/block", path)
            d.sysfs_no_links = sysfs_no_links
            d.populate_all(pcidata)
            devices.append(d)
    return devices
    
def GetNextMountPath():
    i = 1
    while True:
        full_path = '/mnt/volume_{}'.format(str(i).zfill(2))
        if not os.path.ismount(full_path):
            return full_path
        i += 1
 
def TryCreateDisk():
    DETECT_GB = 100
        
    target_disk = None
    devices = GatherDevices()
    for d in devices:
        size = float(d.sectors) * float(d.sectorsize)
        size_gb = size / 1024 / 1024 / 1024
        print(d.diskname, size_gb, len(d.partitions))
        if size_gb > DETECT_GB:
            if len(d.partitions) == 0:
                print("Create Parition", d.diskname, size_gb)
                if size_gb > 2000:
                    os.system('printf "g\nn\n1\n\n\nw\n" | fdisk "/dev/{}"'.format(d.diskname))
                else:
                    os.system('printf "o\nn\np\n1\n\n\nw\n" | fdisk "/dev/{}"'.format(d.diskname))
                target_disk = d.diskname
                break

    if target_disk == None:
        print("Couldn't find disk greater than {}GB and no partition".format(DETECT_GB))
        return False

    devices = GatherDevices()
    for d in devices:
        if d.diskname == target_disk:
            partition = '/dev/{}'.format(d.partitions[0].diskname)
            print("Format Parition ext4", partition)
            os.system('mkfs -t ext4 {}'.format(partition))

    devices = GatherDevices()
    for d in devices:
        if d.diskname == target_disk:
            size = float(d.sectors) * float(d.sectorsize)
            size_gb = size / 1024 / 1024 / 1024
            if size_gb > DETECT_GB:
                assert len(d.partitions) == 1
                for i in range(len(d.partitions)):
                    f = open('/etc/fstab', 'r')
                    fstab_content = f.read()
                    f.close()
                    fstab_content = fstab_content.replace('/dev/disk/cloud/azure_resource-part1    /mnt    auto    defaults,nofail,x-systemd.requires=cloud-init.service,comment=cloudconfig    0    2\n', '')
                    fstab_content = fstab_content.replace('/dev/disk/cloud/azure_resource-part1    /mnt    auto    defaults,nofail,x-systemd.requires=cloud-init.service,_netdev,comment=cloudconfig    0    2\n', '')
                    if not d.uuids[i] in fstab_content:
                        mount_path = GetNextMountPath()
                        if not os.path.exists(mount_path):
                            os.makedirs(mount_path)
                        print("Write to fstab:", d.partitions[i].diskname, size_gb, mount_path)
                        mount_info = 'UUID={} {}          ext4    defaults,nofail,discard 0 0\n'.format(d.uuids[i], mount_path)
                        fstab_content += mount_info
                        f = open('/etc/fstab', 'w')
                        f.write(fstab_content)
                        f.close()
                        print(d.partitions[i].diskname, "temp mount to ", mount_path)
                        os.system("mount /dev/{} {}".format(d.partitions[i].diskname, mount_path))
    return True
    
while True:
    is_has_next = TryCreateDisk()
    print(is_has_next)
    if not is_has_next:
        break
