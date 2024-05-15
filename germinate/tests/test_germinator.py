"""Unit tests for germinate.germinator."""

# Copyright (C) 2012 Canonical Ltd.
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
import shutil

from germinate.archive import TagFile
from germinate.germinator import (
    BuildDependsReason,
    DependsReason,
    ExtraReason,
    GerminatedSeed,
    Germinator,
    RecommendsReason,
    RescueReason,
    SeedReason,
)
from germinate.tests.helpers import TestCase


class TestSeedReason(TestCase):
    def test_str(self):
        """SeedReason stringifies to a description of the seed."""
        reason = SeedReason("branch", "base")
        self.assertEqual("Branch base seed", str(reason))


class TestBuildDependsReason(TestCase):
    def test_str(self):
        """BuildDependsReason stringifies to a description of the reason."""
        reason = BuildDependsReason("foo")
        self.assertEqual("foo (Build-Depend)", str(reason))


class TestRecommendsReason(TestCase):
    def test_str(self):
        """RecommendsReason stringifies to a description of the reason."""
        reason = RecommendsReason("foo")
        self.assertEqual("foo (Recommends)", str(reason))


class TestDependsReason(TestCase):
    def test_str(self):
        """DependsReason stringifies to the package name."""
        reason = DependsReason("foo")
        self.assertEqual("foo", str(reason))


class TestExtraReason(TestCase):
    def test_str(self):
        """ExtraReason stringifies to a description of the reason."""
        reason = ExtraReason("foo")
        self.assertEqual("Generated by foo", str(reason))


class TestRescueReason(TestCase):
    def test_str(self):
        """RescueReason stringifies to a description of the reason."""
        reason = RescueReason("foo")
        self.assertEqual("Rescued from foo", str(reason))


class TestGerminatedSeed(TestCase):
    def test_basic(self):
        """GerminatedSeed has reasonable basic properties."""
        branch = "collection.dist"
        self.addSeed(branch, "one")
        self.addSeedPackage(branch, "one", "one-package")
        structure = self.openSeedStructure(branch)
        seed = GerminatedSeed(None, "one", structure, structure["one"])
        self.assertEqual("one", seed.name)
        self.assertEqual(structure, seed.structure)
        self.assertEqual("one", str(seed))
        self.assertEqual(structure["one"], seed._raw_seed)

    def test_equal_if_same_contents(self):
        """GerminatedSeeds with the same seeds and inheritance are equal."""
        one = "one.dist"
        two = "two.dist"
        self.addSeed(one, "base")
        self.addSeedPackage(one, "base", "base")
        self.addSeed(one, "desktop", parents=["base"])
        self.addSeedPackage(one, "desktop", "desktop")
        self.addSeed(two, "base")
        self.addSeedPackage(two, "base", "base")
        self.addSeed(two, "desktop", parents=["base"])
        self.addSeedPackage(two, "desktop", "desktop")
        structure_one = self.openSeedStructure(one)
        structure_two = self.openSeedStructure(two)
        germinator = Germinator("i386")
        desktop_one = GerminatedSeed(
            germinator, "desktop", structure_one, structure_one["desktop"]
        )
        desktop_two = GerminatedSeed(
            germinator, "desktop", structure_two, structure_two["desktop"]
        )
        self.assertEqual(desktop_one, desktop_two)

    def test_not_equal_if_different_contents(self):
        """GerminatedSeeds with different seeds/inheritance are not equal."""
        one = "one.dist"
        two = "two.dist"
        self.addSeed(one, "base")
        self.addSeedPackage(one, "base", "base")
        self.addSeed(one, "desktop", parents=["base"])
        self.addSeedPackage(one, "desktop", "desktop")
        self.addSeed(two, "base")
        self.addSeedPackage(two, "base", "base")
        self.addSeed(two, "desktop")
        self.addSeedPackage(two, "desktop", "desktop")
        structure_one = self.openSeedStructure(one)
        structure_two = self.openSeedStructure(two)
        germinator = Germinator("i386")
        desktop_one = GerminatedSeed(
            germinator, "desktop", structure_one, structure_one["desktop"]
        )
        desktop_two = GerminatedSeed(
            germinator, "desktop", structure_two, structure_two["desktop"]
        )
        self.assertNotEqual(desktop_one, desktop_two)


class TestGerminator(TestCase):
    def test_parse_archive(self):
        """Germinator.parse_archive successfully parses a simple archive."""
        self.addSource(
            "warty",
            "main",
            "hello",
            "1.0-1",
            ["hello", "hello-dependency"],
            fields={"Maintainer": "Test Person <test@example.com>"},
        )
        self.addPackage(
            "warty",
            "main",
            "i386",
            "hello",
            "1.0-1",
            fields={
                "Maintainer": "Test Person <test@example.com>",
                "Depends": "hello-dependency",
            },
        )
        self.addPackage(
            "warty",
            "main",
            "i386",
            "hello-dependency",
            "1.0-1",
            fields={"Source": "hello", "Multi-Arch": "foreign"},
        )
        self.addSeed("ubuntu.warty", "supported")
        self.addSeedPackage("ubuntu.warty", "supported", "hello")
        germinator = Germinator("i386")
        archive = TagFile(
            "warty", "main", "i386", "file://%s" % self.archive_dir
        )
        germinator.parse_archive(archive)

        self.assertIn("hello", germinator._sources)
        self.assertEqual(
            {
                "Maintainer": "Test Person <test@example.com>",
                "Version": "1.0-1",
                "Build-Depends": [],
                "Build-Depends-Indep": [],
                "Build-Depends-Arch": [],
                "Binaries": ["hello", "hello-dependency"],
            },
            germinator._sources["hello"],
        )
        self.assertIn("hello", germinator._packages)
        self.assertEqual(
            {
                "Section": "",
                "Version": "1.0-1",
                "Maintainer": "Test Person <test@example.com>",
                "Essential": "",
                "Pre-Depends": [],
                "Built-Using": [],
                "Depends": [[("hello-dependency", "", "")]],
                "Recommends": [],
                "Size": 0,
                "Installed-Size": 0,
                "Source": "hello",
                "Provides": [],
                "Kernel-Version": "",
                "Multi-Arch": "none",
                "Architecture": "i386",
            },
            germinator._packages["hello"],
        )
        self.assertEqual("deb", germinator._packagetype["hello"])
        self.assertIn("hello-dependency", germinator._packages)
        self.assertEqual(
            {
                "Section": "",
                "Version": "1.0-1",
                "Maintainer": "",
                "Essential": "",
                "Pre-Depends": [],
                "Built-Using": [],
                "Depends": [],
                "Recommends": [],
                "Size": 0,
                "Installed-Size": 0,
                "Source": "hello",
                "Provides": [],
                "Kernel-Version": "",
                "Multi-Arch": "foreign",
                "Architecture": "i386",
            },
            germinator._packages["hello-dependency"],
        )
        self.assertEqual("deb", germinator._packagetype["hello-dependency"])
        self.assertEqual({}, germinator._provides)

    def test_different_providers_between_suites(self):
        """Provides from later versions override those from earlier ones."""
        self.addSource("warty", "main", "hello", "1.0-1", ["hello"])
        self.addPackage(
            "warty",
            "main",
            "i386",
            "hello",
            "1.0-1",
            fields={"Provides": "goodbye"},
        )
        self.addSource("warty-updates", "main", "hello", "1.0-1.1", ["hello"])
        self.addPackage(
            "warty-updates",
            "main",
            "i386",
            "hello",
            "1.0-1.1",
            fields={"Provides": "hello-goodbye"},
        )
        germinator = Germinator("i386")
        archive = TagFile(
            ["warty", "warty-updates"],
            "main",
            "i386",
            "file://%s" % self.archive_dir,
        )
        germinator.parse_archive(archive)

        self.assertNotIn("goodbye", germinator._provides)
        self.assertIn("hello-goodbye", germinator._provides)
        self.assertEqual({"hello": ""}, germinator._provides["hello-goodbye"])

    def test_depends_multiarch(self):
        """Compare Depends behaviour against the multiarch specification.

        https://wiki.ubuntu.com/MultiarchSpec
        """
        for ma, qual, allowed in (
            (None, "", True),
            (None, ":any", False),
            (None, ":native", False),
            ("same", "", True),
            ("same", ":any", False),
            ("same", ":native", False),
            ("foreign", "", True),
            ("foreign", ":any", False),
            ("foreign", ":native", False),
            ("allowed", "", True),
            ("allowed", ":any", True),
            ("allowed", ":native", False),
        ):
            self.addSource("precise", "main", "hello", "1.0-1", ["hello"])
            self.addPackage(
                "precise",
                "main",
                "i386",
                "hello",
                "1.0-1",
                fields={"Depends": "gettext%s" % qual},
            )
            self.addSource(
                "precise", "main", "gettext", "0.18.1.1-5ubuntu3", ["gettext"]
            )
            package_fields = {}
            if ma is not None:
                package_fields["Multi-Arch"] = ma
            self.addPackage(
                "precise",
                "main",
                "i386",
                "gettext",
                "0.18.1.1-5ubuntu3",
                fields=package_fields,
            )
            branch = "collection.precise"
            self.addSeed(branch, "base")
            self.addSeedPackage(branch, "base", "hello")
            germinator = Germinator("i386")
            archive = TagFile(
                "precise", "main", "i386", "file://%s" % self.archive_dir
            )
            germinator.parse_archive(archive)
            structure = self.openSeedStructure(branch)
            germinator.plant_seeds(structure)
            germinator.grow(structure)

            expected = set()
            if allowed:
                expected.add("gettext")
            self.assertEqual(
                expected,
                germinator.get_depends(structure, "base"),
                "Depends: gettext%s on Multi-Arch: %s incorrectly %s"
                % (
                    qual,
                    ma if ma else "none",
                    "disallowed" if allowed else "allowed",
                ),
            )

            shutil.rmtree(self.archive_dir)
            shutil.rmtree(self.seeds_dir)

    def test_build_depends_multiarch(self):
        """Compare Build-Depends behaviour against the multiarch specification.

        https://wiki.ubuntu.com/MultiarchCross#Build_Dependencies
        """
        for ma, qual, allowed in (
            (None, "", True),
            (None, ":any", False),
            (None, ":native", True),
            ("same", "", True),
            ("same", ":any", False),
            ("same", ":native", True),
            ("foreign", "", True),
            ("foreign", ":any", False),
            ("foreign", ":native", False),
            ("allowed", "", True),
            ("allowed", ":any", True),
            ("allowed", ":native", True),
        ):
            self.addSource(
                "precise",
                "main",
                "hello",
                "1.0-1",
                ["hello"],
                fields={"Build-Depends": "gettext%s" % qual},
            )
            self.addPackage("precise", "main", "i386", "hello", "1.0-1")
            self.addSource(
                "precise", "main", "gettext", "0.18.1.1-5ubuntu3", ["gettext"]
            )
            package_fields = {}
            if ma is not None:
                package_fields["Multi-Arch"] = ma
            self.addPackage(
                "precise",
                "main",
                "i386",
                "gettext",
                "0.18.1.1-5ubuntu3",
                fields=package_fields,
            )
            branch = "collection.precise"
            self.addSeed(branch, "base")
            self.addSeedPackage(branch, "base", "hello")
            germinator = Germinator("i386")
            archive = TagFile(
                "precise", "main", "i386", "file://%s" % self.archive_dir
            )
            germinator.parse_archive(archive)
            structure = self.openSeedStructure(branch)
            germinator.plant_seeds(structure)
            germinator.grow(structure)

            expected = set()
            if allowed:
                expected.add("gettext")
            self.assertEqual(
                expected,
                germinator.get_build_depends(structure, "base"),
                "Build-Depends: gettext%s on Multi-Arch: %s incorrectly %s"
                % (
                    qual,
                    ma if ma else "none",
                    "disallowed" if allowed else "allowed",
                ),
            )

            shutil.rmtree(self.archive_dir)
            shutil.rmtree(self.seeds_dir)

    def test_build_depends_all(self):
        """Confirm build-depends of arch: all packages are recursed when
        follow-build-depends-all is set, and not when
        no-follow-build-depends-all is set.
        """
        self.addSource(
            "focal",
            "main",
            "hello",
            "1.0-1",
            ["hello"],
            fields={"Build-Depends": "gettext"},
        )
        self.addPackage(
            "focal",
            "main",
            "i386",
            "hello",
            "1.0-1",
            fields={"Architecture": "all"},
        )
        self.addSource(
            "focal", "main", "gettext", "0.18.1.1-5ubuntu3", ["gettext"]
        )
        self.addPackage(
            "focal", "main", "i386", "gettext", "0.18.1.1-5ubuntu3"
        )
        branch = "collection.focal"
        archive = TagFile(
            "focal", "main", "i386", "file://%s" % self.archive_dir
        )
        for sense in ("no-", ""):
            self.addSeed(branch, "base")
            self.addSeedPackage(branch, "base", "hello")
            self.addStructureLine(
                branch, "feature %sfollow-build-depends-all" % sense
            )
            germinator = Germinator("i386")
            germinator.parse_archive(archive)
            structure = self.openSeedStructure(branch)
            germinator.plant_seeds(structure)
            germinator.grow(structure)

            expected = set()
            if sense == "":
                expected.add("gettext")
            self.assertEqual(
                expected,
                germinator.get_build_depends(structure, "base"),
                "Build-Depends: gettext from Architecture: all package "
                "incorrectly %s" % "included"
                if sense == "no-"
                else "omitted",
            )

            shutil.rmtree(self.seeds_dir)
        shutil.rmtree(self.archive_dir)

    def test_build_depends_profiles(self):
        """Test that https://wiki.debian.org/BuildProfileSpec restrictions
        are parseable.
        """
        self.addSource(
            "precise",
            "main",
            "hello",
            "1.0-1",
            ["hello"],
            fields={
                "Build-Depends": "gettext <!stage1> <!cross>, "
                "base-files <stage1>, "
                "gettext (<< 0.7) | debhelper (>= 9)"
            },
        )
        self.addPackage("precise", "main", "i386", "hello", "1.0-1")
        self.addSource(
            "precise", "main", "gettext", "0.8.1.1-5ubuntu3", ["gettext"]
        )
        self.addPackage(
            "precise", "main", "i386", "gettext", "0.8.1.1-5ubuntu3"
        )
        self.addSource(
            "precise", "main", "base-files", "6.5ubuntu6", ["base-files"]
        )
        self.addPackage("precise", "main", "i386", "base-files", "6.5ubuntu6")
        self.addSource(
            "precise", "main", "debhelper", "9.20120115ubuntu3", ["debhelper"]
        )
        self.addPackage(
            "precise", "main", "i386", "debhelper", "9.20120115ubuntu3"
        )
        branch = "collection.precise"
        self.addSeed(branch, "base")
        self.addSeedPackage(branch, "base", "hello")
        germinator = Germinator("i386")
        archive = TagFile(
            "precise", "main", "i386", "file://%s" % self.archive_dir
        )
        germinator.parse_archive(archive)
        structure = self.openSeedStructure(branch)
        germinator.plant_seeds(structure)
        germinator.grow(structure)

        self.assertEqual(
            {"gettext", "debhelper"},
            germinator.get_build_depends(structure, "base"),
        )

    def test_versioned_provides(self):
        """Germinator.parse_archive resolves versioned provides."""
        self.addSource(
            "bionic",
            "main",
            "hello",
            "1.0-1",
            ["hello", "hello-dependency", "hello-bad"],
            fields={"Maintainer": "Test Person <test@example.com>"},
        )
        self.addPackage(
            "bionic",
            "main",
            "i386",
            "hello",
            "1.0-1",
            fields={
                "Maintainer": "Test Person <test@example.com>",
                "Depends": "hello-virtual (>= 2.0)",
            },
        )
        self.addPackage(
            "bionic",
            "main",
            "i386",
            "hello-bad",
            "2.0-1",
            fields={
                "Source": "hello (= 1.0-1)",
                "Provides": "hello-virtual (= 1.0)",
            },
        )
        self.addPackage(
            "bionic",
            "main",
            "i386",
            "hello-dependency",
            "1.0-1",
            fields={"Source": "hello", "Provides": "hello-virtual (= 2.0)"},
        )
        branch = "ubuntu.bionic"
        self.addSeed(branch, "supported")
        self.addSeedPackage(branch, "supported", "hello")
        germinator = Germinator("i386")
        archive = TagFile(
            "bionic", "main", "i386", "file://%s" % self.archive_dir
        )
        germinator.parse_archive(archive)

        self.assertIn("hello", germinator._sources)
        self.assertIn("hello", germinator._packages)
        self.assertEqual("deb", germinator._packagetype["hello"])
        self.assertIn("hello-dependency", germinator._packages)
        self.assertEqual("deb", germinator._packagetype["hello-dependency"])
        self.assertIn("hello-bad", germinator._packages)
        self.assertEqual("deb", germinator._packagetype["hello-bad"])
        self.assertEqual(
            {"hello-virtual": {"hello-bad": "1.0", "hello-dependency": "2.0"}},
            germinator._provides,
        )
        structure = self.openSeedStructure(branch)
        germinator.plant_seeds(structure)
        germinator.grow(structure)

        expected = {"hello-dependency"}
        self.assertEqual(
            expected, germinator.get_depends(structure, "supported")
        )

    def test_snap(self):
        branch = "collection.precise"
        self.addSeed(branch, "base")
        self.addSeedSnap(branch, "base", "hello")
        germinator = Germinator("i386")
        structure = self.openSeedStructure(branch)
        germinator.plant_seeds(structure)
        germinator.grow(structure)

        self.assertEqual({"hello"}, germinator.get_snaps(structure, "base"))

    def test_snap_recommends(self):
        branch = "collection.precise"
        self.addSeed(branch, "base")
        self.addSeedSnap(branch, "base", "(hello)")
        with self.assertLogs("germinate", level=logging.WARNING) as logs:
            germinator = Germinator("i386")
            structure = self.openSeedStructure(branch)
            germinator.plant_seeds(structure)
            germinator.grow(structure)
        self.assertIn("ignoring hello", logs.output[0])

        self.assertEqual(set(), germinator.get_snaps(structure, "base"))

    def test_alternatives(self):
        """Check the behavior with alternatives for seeds.

        Alternatives should not appear in the seed entries, but must exist
        in the archive as a real or virtual package, and can be queried using
        `Germinator.get_seed_alternatives()`
        """
        self.addSource(
            "precise", "main", "hello", "1.0-1", ["hello", "hello-alternative"]
        )
        self.addPackage(
            "precise",
            "main",
            "i386",
            "hello",
            "1.0-1",
            fields={"Provides": "some-hello"},
        )
        self.addPackage(
            "precise",
            "main",
            "i386",
            "hello-alternative",
            "1.0-1",
            fields={"Provides": "some-hello"},
        )

        branch = "collection.precise"
        self.addSeed(branch, "base")
        self.addSeedPackage(
            branch,
            "base",
            "hello | hello-alternative | some-hello | does-not-exist",
        )
        germinator = Germinator("i386")
        archive = TagFile(
            "precise", "main", "i386", "file://%s" % self.archive_dir
        )
        germinator.parse_archive(archive)
        structure = self.openSeedStructure(branch)
        with self.assertLogs() as logs:
            germinator.plant_seeds(structure)
        germinator.grow(structure)
        self.assertEqual(
            logs.output,
            [
                "ERROR:germinate.germinator:Unknown alternative package: "
                "does-not-exist"
            ],
        )
        self.assertEqual(
            ["hello"], germinator.get_seed_entries(structure, "base")
        )
        self.assertEqual(
            {"hello": ["hello-alternative", "some-hello"]},
            germinator.get_seed_alternatives(structure, "base"),
        )

    # TODO: Germinator needs many more unit tests.
