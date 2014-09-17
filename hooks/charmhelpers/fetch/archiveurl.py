import os
import urllib2
from urllib import urlretrieve
import urlparse
import hashlib

from charmhelpers.fetch import (
    BaseFetchHandler,
    UnhandledSource
)
from charmhelpers.payload.archive import (
    get_archive_handler,
    extract,
)
from charmhelpers.core.host import mkdir

"""
This class is a plugin for charmhelpers.fetch.install_remote.

It grabs, validates and installs remote archives fetched over "http", "https", "ftp" or "file" protocols. The contents of the archive are installed in $CHARM_DIR/fetched/.

Example usage:
install_remote("https://example.com/some/archive.tar.gz")
# Installs the contents of archive.tar.gz in $CHARM_DIR/fetched/.

See charmhelpers.fetch.archiveurl.get_archivehandler for supported archive types.
"""
class ArchiveUrlFetchHandler(BaseFetchHandler):
    """Handler for archives via generic URLs"""
    def can_handle(self, source):
        url_parts = self.parse_url(source)
        if url_parts.scheme not in ('http', 'https', 'ftp', 'file'):
            return "Wrong source type"
        if get_archive_handler(self.base_url(source)):
            return True
        return False

    def download(self, source, dest):
        # propogate all exceptions
        # URLError, OSError, etc
        proto, netloc, path, params, query, fragment = urlparse.urlparse(source)
        if proto in ('http', 'https'):
            auth, barehost = urllib2.splituser(netloc)
            if auth is not None:
                source = urlparse.urlunparse((proto, barehost, path, params, query, fragment))
                username, password = urllib2.splitpasswd(auth)
                passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
                # Realm is set to None in add_password to force the username and password
                # to be used whatever the realm
                passman.add_password(None, source, username, password)
                authhandler = urllib2.HTTPBasicAuthHandler(passman)
                opener = urllib2.build_opener(authhandler)
                urllib2.install_opener(opener)
        response = urllib2.urlopen(source)
        try:
            with open(dest, 'w') as dest_file:
                dest_file.write(response.read())
        except Exception as e:
            if os.path.isfile(dest):
                os.unlink(dest)
            raise e

    def install(self, source):
        url_parts = self.parse_url(source)
        dest_dir = os.path.join(os.environ.get('CHARM_DIR'), 'fetched')
        if not os.path.exists(dest_dir):
            mkdir(dest_dir, perms=0755)
        dld_file = os.path.join(dest_dir, os.path.basename(url_parts.path))
        try:
            self.download(source, dld_file)
        except urllib2.URLError as e:
            raise UnhandledSource(e.reason)
        except OSError as e:
            raise UnhandledSource(e.strerror)
        return extract(dld_file)

    # Mandatory file validation via Sha1 or MD5 hashing.
    def download_and_validate(self, url, hashsum, validate="sha1"):
        if validate == 'sha1' and len(hashsum) != 40:
            raise ValueError("HashSum must be = 40 characters when using sha1"
                             " validation")
        if validate == 'md5' and len(hashsum) != 32:
            raise ValueError("HashSum must be = 32 characters when using md5"
                             " validation")
        tempfile, headers = urlretrieve(url)
        self.validate_file(tempfile, hashsum, validate)
        return tempfile

    # Predicate method that returns status of hash matching expected hash.
    def validate_file(self, source, hashsum, vmethod='sha1'):
        if vmethod != 'sha1' and vmethod != 'md5':
            raise ValueError("Validation Method not supported")

        if vmethod == 'md5':
            m = hashlib.md5()
        if vmethod == 'sha1':
            m = hashlib.sha1()
        with open(source) as f:
            for line in f:
                m.update(line)
        if hashsum != m.hexdigest():
            msg = "Hash Mismatch on {} expected {} got {}"
            raise ValueError(msg.format(source, hashsum, m.hexdigest()))
