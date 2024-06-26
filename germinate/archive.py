"""Representations of archives for use by Germinate."""

# Copyright (c) 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012
#               Canonical Ltd.
#
# Germinate is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2, or (at your option) any
# later version.
#
# Germinate is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Germinate; see the file COPYING.  If not, write to the Free
# Software Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA
# 02110-1301, USA.

import logging
import os
import shutil
import subprocess
import tempfile
from contextlib import closing
from urllib.parse import quote
from urllib.request import Request, urlopen

import apt_pkg

_logger = logging.getLogger(__name__)


def _progress(msg, *args, **kwargs):
    _logger.info(msg, *args, extra={"progress": True}, **kwargs)


class IndexType:
    """Types of archive index files."""

    PACKAGES = 1
    SOURCES = 2
    INSTALLER_PACKAGES = 3


class Archive:
    """An abstract representation of an archive for use by Germinate."""

    def sections(self):
        """Yield a sequence of the index sections found in this archive.

        A section is an entry in an index file corresponding to a single binary
        or source package.

        Each yielded value should be an (IndexType, section) pair, where
        section is a dictionary mapping control file keys to their values.

        """
        raise NotImplementedError


class TagFile(Archive):
    """Fetch package lists from a Debian-format archive as apt tag files."""

    def __init__(
        self,
        dists,
        components,
        arch,
        mirrors,
        source_mirrors=None,
        installer_packages=True,
        cleanup=False,
    ):
        """Create a representation of a Debian-format apt archive."""
        if isinstance(dists, str):
            dists = [dists]
        if isinstance(components, str):
            components = [components]
        if isinstance(mirrors, str):
            mirrors = [mirrors]
        if isinstance(source_mirrors, str):
            source_mirrors = [source_mirrors]

        self._dists = dists
        self._components = components
        self._arch = arch
        self._mirrors = mirrors
        self._installer_packages = installer_packages
        if source_mirrors:
            self._source_mirrors = source_mirrors
        else:
            self._source_mirrors = mirrors
        self._cleanup = cleanup

    def _open_tag_files(
        self, mirrors, dirname, tagfile_type, dist, component, ftppath
    ):
        def _open_tag_file(mirror, suffix):
            """Download an apt tag file if needed, then open it."""
            if not mirror.endswith("/"):
                mirror += "/"
            url = (
                mirror
                + "dists/"
                + dist
                + "/"
                + component
                + "/"
                + ftppath
                + suffix
            )
            req = Request(url)
            filename = None

            if req.type != "file":
                filename = "%s_%s_%s_%s" % (
                    quote(mirror, safe=""),
                    quote(dist, safe=""),
                    component,
                    tagfile_type,
                )
            else:
                # Make a more or less dummy filename for local URLs.
                filename = os.path.split(req.selector)[0].replace(os.sep, "_")

            fullname = os.path.join(dirname, filename)
            if req.type == "file":
                # Always refresh.  TODO: we should use If-Modified-Since for
                # remote HTTP tag files.
                try:
                    os.unlink(fullname)
                except OSError:
                    pass
            if not os.path.exists(fullname):
                _progress("Downloading %s file ...", req.get_full_url())

                compressed = os.path.join(dirname, filename + suffix)
                try:
                    with closing(urlopen(req)) as url_f, open(
                        compressed, "wb"
                    ) as compressed_f:
                        compressed_f.write(url_f.read())

                    # apt_pkg is weird and won't accept GzipFile
                    if suffix:
                        _progress(
                            "Decompressing %s file ...", req.get_full_url()
                        )

                        if suffix == ".gz":
                            import gzip

                            decompressor = gzip.GzipFile
                        elif suffix == ".bz2":
                            import bz2

                            decompressor = bz2.BZ2File
                        elif suffix == ".xz":
                            import lzma

                            decompressor = lzma.LZMAFile
                        else:
                            raise RuntimeError("Unknown suffix '%s'" % suffix)

                        with decompressor(compressed) as compressed_f:
                            with open(fullname, "wb") as f:
                                f.write(compressed_f.read())
                                f.flush()
                finally:
                    if suffix:
                        try:
                            os.unlink(compressed)
                        except OSError:
                            pass

            return open(fullname, encoding="UTF-8", errors="replace")

        tag_files = []
        for mirror in mirrors:
            tag_file = None
            for suffix in (".xz", ".bz2", ".gz", ""):
                try:
                    tag_file = _open_tag_file(mirror, suffix)
                    tag_files.append(tag_file)
                    break
                except OSError:
                    pass
        if len(tag_files) == 0:
            raise OSError("no %s files found" % tagfile_type)
        return tag_files

    def sections(self):
        """Yield a sequence of the index sections found in this archive.

        A section is an entry in an index file corresponding to a single binary
        or source package.

        Each yielded value is an (IndexType, section) pair, where section is
        a dictionary mapping control file keys to their values.

        """
        if self._cleanup:
            dirname = tempfile.mkdtemp(prefix="germinate-")
        else:
            dirname = "."

        try:
            for dist in self._dists:
                for component in self._components:
                    packages = self._open_tag_files(
                        self._mirrors,
                        dirname,
                        "Packages",
                        dist,
                        component,
                        "binary-" + self._arch + "/Packages",
                    )
                    for tag_file in packages:
                        try:
                            for section in apt_pkg.TagFile(tag_file):
                                yield (IndexType.PACKAGES, section)
                        finally:
                            tag_file.close()

                    sources = self._open_tag_files(
                        self._source_mirrors,
                        dirname,
                        "Sources",
                        dist,
                        component,
                        "source/Sources",
                    )
                    for tag_file in sources:
                        try:
                            for section in apt_pkg.TagFile(tag_file):
                                yield (IndexType.SOURCES, section)
                        finally:
                            tag_file.close()

                    instpackages = ""
                    if self._installer_packages:
                        try:
                            instpackages = self._open_tag_files(
                                self._mirrors,
                                dirname,
                                "InstallerPackages",
                                dist,
                                component,
                                "debian-installer/binary-"
                                + self._arch
                                + "/Packages",
                            )
                        except OSError:
                            # can live without these
                            _progress(
                                "Missing installer Packages file for %s "
                                "(ignoring)",
                                component,
                            )
                        else:
                            for tag_file in instpackages:
                                try:
                                    for section in apt_pkg.TagFile(tag_file):
                                        yield (
                                            IndexType.INSTALLER_PACKAGES,
                                            section,
                                        )
                                finally:
                                    tag_file.close()
        finally:
            if self._cleanup:
                shutil.rmtree(dirname)


class AptArchive(Archive):
    def __init__(self, config_path):
        self.config_path = config_path

    def _get_files(self, identifier):
        env = dict(os.environ, APT_CONFIG=self.config_path)
        cmd = [
            "apt-get",
            "indextargets",
            "--format",
            "$(FILENAME)",
            "Identifier: " + identifier,
        ]
        cp = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        return cp.stdout.splitlines()

    def sections(self):
        for filename in self._get_files("Packages"):
            _progress(
                "processing packages file %s ...",
                filename,
            )
            with open(
                filename, encoding="UTF-8", errors="replace"
            ) as file_obj:
                for section in apt_pkg.TagFile(file_obj):
                    yield (IndexType.PACKAGES, section)
        for filename in self._get_files("Sources"):
            _progress(
                "processing sources file %s ...",
                filename,
            )
            with open(
                filename, encoding="UTF-8", errors="replace"
            ) as file_obj:
                for section in apt_pkg.TagFile(file_obj):
                    yield (IndexType.SOURCES, section)
