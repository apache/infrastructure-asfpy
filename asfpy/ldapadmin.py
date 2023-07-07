#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" ASF LDAP Account Manager """

if not __debug__:
    raise RuntimeError("This code requires Assertions to be enabled")

import sys
assert sys.version_info >= (3, 2)

import ldap
import ldap.modlist
import ldif
import re
import crypt
import random
import string

LDAP_SANDBOX = "ldaps://ldap-sandbox.apache.org:636"
LDAP_MASTER = "ldaps://ldap-us.apache.org:636"
LDAP_SUFFIX = 'dc=apache,dc=org'
LDAP_PEOPLE_BASE = 'ou=people,dc=apache,dc=org'
LDAP_GROUPS_BASE = 'ou=groups,dc=apache,dc=org'
LDAP_APLDAP_BASE = 'cn=apldap,ou=groups,ou=services,dc=apache,dc=org'
LDAP_CHAIRS_BASE = 'cn=pmc-chairs,ou=groups,ou=services,dc=apache,dc=org'
LDAP_PMCS_BASE = 'ou=project,ou=groups,dc=apache,dc=org'
LDAP_ROLES_BASE = 'ou=role,ou=groups,dc=apache,dc=org'
LDAP_DN = 'uid=%s,ou=people,dc=apache,dc=org'
LDAP_CN = 'cn=%s,%s'

# INFRA-21590 ApacheID cannot have dashes.
LDAP_VALID_UID_RE = re.compile(r"^[a-z0-9][a-z0-9_]+$")
# New user account UIDs will be larger than this value.
# Conversely: service accounts will be less than this.
# NOTE: this value was chosen to ensure enough lower-value
#       UIDs were available for service accounts, until we
#       reach the heat death of the universe.
MINIMUM_USER_UID = 6000

# New service account UIDs will be larger than this value,
# but below that of MINIMUM_UID.
# NOTE: since the GID is chosen to match the UID, we start
#       at 5010, to avoid collision with: "nacho" uid=1122 gid=5004
MINIMUM_SVC_UID = 5010

assert MINIMUM_USER_UID > MINIMUM_SVC_UID

ASSERTION_FAILED = "Common backend assertions failed, LDAP corruption?"
BACKEND_TIMEOUT = "The backend authentication server timed out, please retry later."

def bytify(ldiff):
    """ Convert all values in a dict to byte-string """
    for k, v in ldiff.items():
        if type(v) is list:
            n = 0
            for xv in v:
                if type(v[n]) is str:
                    v[n] = xv.encode('utf-8')
                n += 1
        else:
            if type(v) is str:
                v = [v.encode('utf-8')]
        ldiff[k] = v
    return ldiff


def stringify(ldiff):
    """ Convert all values in a dict to string """
    for k, v in ldiff.items():
        # Convert single-list to string
        if type(v) is list and len(v) == 1:
            v = v[0]

        if type(v) is list:
            n = 0
            for xv in v:
                if type(v[n]) is bytes:
                    v[n] = xv.decode('utf-8')
                n += 1
        else:
            if type(v) is bytes:
                v = v.decode('utf-8')
        ldiff[k] = v
    return ldiff


class ConnectionException(Exception):
    """ Simple exception with a message and an optional origin exception (WIP) """
    def __init__(self, message, origin=None):
        super().__init__(message)
        self.origin = origin


class ValidatorException(Exception):
    """ Simple validator exception with a message and an optional triggering attribute """
    def __init__(self, message, attrib=None):
        super().__init__(message)
        self.attribute = attrib


class committer:
    """ Committer class, allows for munging data """

    def __init__(self, mgr, res):
        self.manager = mgr
        self.dn = res[0][0]
        self.dn_enc = self.dn.encode('ascii')
        self.attributes = stringify(res[0][1])
        self.uid = self.attributes['uid']

    def add_project(self, project):
        """ Add person to project (as committer) """
        dn = LDAP_CN % (project, LDAP_PMCS_BASE)
        self.manager.lc.modify_s(dn, [(ldap.MOD_ADD, 'member', self.dn_enc)])

    def add_pmc(self, project):
        """ Add person to project (as PMC member) """
        dn = LDAP_CN % (project, LDAP_PMCS_BASE)
        self.manager.lc.modify_s(dn, [(ldap.MOD_ADD, 'owner', self.dn_enc)])

    def add_basic_group(self, group):
        """ Add person to basic posixGroup entry """
        dn = LDAP_CN % (group, LDAP_GROUPS_BASE)
        self.manager.lc.modify_s(dn, [(ldap.MOD_ADD, 'memberUid', self.uid.encode('ascii'))])

    def add_role(self, role):
        """ Add person to basic posixGroup entry """
        dn = LDAP_CN % (role, LDAP_ROLES_BASE)
        self.manager.lc.modify_s(dn, [(ldap.MOD_ADD, 'member', self.dn_enc)])

    def remove_project(self, project):
        """ Remove person from project (as committer) """
        dn = LDAP_CN % (project, LDAP_PMCS_BASE)
        self.manager.lc.modify_s(dn, [(ldap.MOD_DELETE, 'member', self.dn_enc)])

    def remove_pmc(self, project):
        """ Remove person from PMC """
        dn = LDAP_CN % (project, LDAP_PMCS_BASE)
        self.manager.lc.modify_s(dn, [(ldap.MOD_DELETE, 'owner', self.dn_enc)])

    def remove_basic_group(self, group):
        """ Remove person from basic posixGroup entry """
        dn = LDAP_CN % (group, LDAP_GROUPS_BASE)
        self.manager.lc.modify_s(dn, [(ldap.MOD_DELETE, 'memberUid', self.uid.encode('ascii'))])

    def remove_role(self, role):
        """ Add person to basic posixGroup entry """
        dn = LDAP_CN % (role, LDAP_ROLES_BASE)
        self.manager.lc.modify_s(dn, [(ldap.MOD_DELETE, 'member', self.dn_enc)])

    def rename(self, newuid):
        """ Rename an account, fixing in all projects """
        xuid = newuid
        if type(newuid) is str:
            newuid = newuid.encode('ascii')
        else:
            xuid = newuid.decode('ascii')
        # Validate uid
        if not LDAP_VALID_UID_RE.match(xuid):
            raise ValidatorException("Invalid UID, must match ^[a-z0-9][a-z0-9_]+$")

        # Test if uid exists
        if self.manager.load_account(xuid):
            raise ConnectionException("An account with this uid already exists")

        # Test for clashing cn's
        res = self.manager.lc.search_s(LDAP_SUFFIX, ldap.SCOPE_SUBTREE, 'cn=%s' % xuid)
        if res:
            raise ValidatorException("availid clashes with project name %s!" % res[0][0], 'uid')

        # Switch email and home dir
        changeset = []
        o_email = self.attributes['asf-committer-email'].encode('ascii')
        n_email = b'%s@apache.org' % newuid
        o_homedir = self.attributes['homeDirectory'].encode('ascii')
        n_homedir = b'/home/%s' % newuid
        changeset.append((ldap.MOD_DELETE, 'asf-committer-email', o_email))
        changeset.append((ldap.MOD_ADD, 'asf-committer-email', n_email))
        changeset.append((ldap.MOD_DELETE, 'homeDirectory', o_homedir))
        changeset.append((ldap.MOD_ADD, 'homeDirectory', n_homedir))
        self.manager.lc.modify_s(self.dn, changeset)

        # Change DN
        odn = self.dn_enc.decode('ascii')
        newdn = LDAP_DN % xuid
        newdn_enc = newdn.encode('ascii')
        print("Changing %s to %s" % (odn, newdn))
        self.manager.lc.modrdn_s(odn, 'uid=%s' % xuid)
        
        # Search and rename in LDAP groups
        self.manager.redirect_uid(self.uid, newuid)

        # Change in-object
        self.uid = xuid
        self.dn_enc = newdn_enc


class manager:

    """ Top LDAP Manager class for whomever is using the script """
    def __init__(self, user, password, host=LDAP_SANDBOX):
        # Verify correct user ID syntax, construct DN
        if not re.match(r"^[-_a-z0-9]+$", user):
            raise ConnectionException("Invalid characters in User ID. Must be alphanumerical or dashes only.")

        # Init LDAP connection
        lc = ldap.initialize(host)

        lc.set_option(ldap.OPT_REFERRALS, 0)
        lc.set_option(ldap.OPT_TIMEOUT, 5)

        # Attempt to bind with user and pass provided
        try:
            lc.simple_bind_s(LDAP_DN % user, password)
        except ldap.INVALID_CREDENTIALS:
            raise ConnectionException("Invalid username or password supplied!")
        except ldap.TIMEOUT:
            raise ConnectionException(BACKEND_TIMEOUT)

        # So far so good, set uid
        self.uid = user
        self.dn = LDAP_DN % user
        self.lc = lc

        # Get full name etc
        try:
            res = lc.search_s(LDAP_DN % user, ldap.SCOPE_BASE)
            assert(len(res) == 1)
            assert(len(res[0]) == 2)
            fn = res[0][1].get('cn')
            assert(type(fn) is list and len(fn) == 1)
            self.fullname = str(fn[0], 'utf-8')
            self.email = '%s@apache.org' % user
        except ldap.TIMEOUT:
            raise ConnectionException(BACKEND_TIMEOUT)
        except AssertionError:
            raise ConnectionException(ASSERTION_FAILED)

        # Get apldap status
        try:
            res = lc.search_s(LDAP_APLDAP_BASE, ldap.SCOPE_BASE)
            assert(len(res) == 1)
            assert(len(res[0]) == 2)
            members = res[0][1].get('member')
            assert(type(members) is list and len(members) > 0)
            self.isAdmin = bytes(LDAP_DN % user, 'utf-8') in members
        except ldap.TIMEOUT:
            raise ConnectionException(BACKEND_TIMEOUT)
        except AssertionError:
            raise ConnectionException(ASSERTION_FAILED)

    def load_account(self, uid):
        if type(uid) is bytes:
            uid = uid.decode('ascii')
        # Check if account exists!
        res = self.lc.search_s(LDAP_PEOPLE_BASE, ldap.SCOPE_SUBTREE, 'uid=%s' % uid)
        if res:
            return committer(self, res)
        return None

    def _find_gaps(self, l):
        return [item for item in range(l[0], l[-1]+1) if item not in l]

    def next_user_uid(self):
        """ Find lowest available user account uid with a matching available gid """

        try:
            r = self.lc.search_s(LDAP_PEOPLE_BASE, ldap.SCOPE_SUBTREE, 'uid=*', ['uidNumber', 'gidNumber'])
            un_avail_uids = sorted([int(item[1]["uidNumber"][0].decode('utf8')) for item in r])
            un_avail_gids = sorted([int(item[1]["gidNumber"][0].decode('utf8')) for item in r])
            avail_uids = self._find_gaps(un_avail_uids)
            avail_gids = self._find_gaps(un_avail_gids)

            # In case there are no gaps, increment the last returned UID
            # If the new UID is not unavailable append it to the list of
            # available_uids.
            n_uid = int(un_avail_uids[-1]+1)
            while n_uid in un_avail_gids:
                n_uid+=1

            avail_uids.append(n_uid)

            # Ensure you got something
            assert(type(avail_uids) is list and len(avail_uids) > 0 and type(avail_gids) is list and len(avail_gids) > 0)

            for uid in avail_uids:
                if uid >= MINIMUM_USER_UID and uid in avail_gids:
                    return(uid)
                continue

        except ldap.TIMEOUT:
            raise ConnectionException(BACKEND_TIMEOUT)
        except AssertionError:
            raise ConnectionException(ASSERTION_FAILED)

    def create_account(
        self,
        uid,
        email,
        fullname,
        forcePass=None,
        requireTwo=True,
    ):
        """ Attempts to create a committer account in LDAP """
        if not self.isAdmin:
            raise ConnectionException("You do not have sufficient access to create accounts")

        # Validate uid
        if not LDAP_VALID_UID_RE.match(uid):
            raise ValidatorException("Invalid UID, must match ^[a-z0-9][a-z0-9_]+$")

        # Test if uid exists
        if self.load_account(uid):
            raise ConnectionException("An account with this uid already exists")

        # Test for clashing cn's
        res = self.lc.search_s(LDAP_SUFFIX, ldap.SCOPE_SUBTREE, 'cn=%s' % uid)
        if res:
            raise ValidatorException("availid clashes with project name %s!" % res[0][0], 'uid')

        uidnumber = self.next_user_uid()

        # Get surname and given name, validate against spurious whitespace
        names = fullname.split(' ')
        if len(names) < 2 and requireTwo:
            raise ValidatorException("Full name needs at least two parts!", 'fullname')
        givenName = names[0]
        surName = names[-1]
        for n in names:
            if not n.strip():
                raise ValidatorException("Found part of name with too much spacing!", 'fullname')

        # Validate email
        if not re.match(r"^\S+@\S+?\.\S+$", email):
            raise ValidatorException("Invalid email address supplied!", 'email')

        # Set password, b64-encoded crypt of random string
        password = ''.join(random.choice(string.ascii_letters + string.digits) for i in range(16))
        if forcePass:
            password = forcePass
        password_crypted = crypt.crypt(password, crypt.mksalt(method=crypt.METHOD_MD5))

        ldiff = {
            'objectClass': ['person', 'top', 'posixAccount', 'organizationalPerson', 'inetOrgPerson', 'asf-committer', 'hostObject', 'ldapPublicKey'],
            'loginShell': '/bin/bash',
            'asf-sascore': '10',
            'givenName': givenName,
            'sn': surName,
            'mail': email,
            'gidNumber': '9000',
            'uidNumber': str(uidnumber),
            'asf-committer-email': '%s@apache.org' % uid,
            'cn': fullname,
            'homeDirectory': '/home/%s' % uid,
            'userPassword': '{CRYPT}' + password_crypted,
            'host': 'home.apache.org',
        }

        # Convert everything to bytestrings because ldap demands it...
        bytify(ldiff)

        # Run LDIF on server
        dn = LDAP_DN % uid
        am = ldap.modlist.addModlist(ldiff)
        self.lc.add_s(dn, am)

        return self.load_account(uid)

    def redirect_uid(self, from_uid: str, to_uid: str):
        """Redirects auth granted from one userid to another, such as would happen in renames"""
        # Ensure we have strings, not bytestrings
        if isinstance(from_uid, bytes):
            from_uid = from_uid.decode('ascii')
        if isinstance(to_uid, bytes):
            to_uid = to_uid.decode('ascii')

        # Validate from_uid and to_uid
        if not LDAP_VALID_UID_RE.match(from_uid):
            raise ValidatorException(f"Invalid UID '{from_uid}', must match ^[a-z0-9][a-z0-9_]+$")
        if not LDAP_VALID_UID_RE.match(to_uid):
            raise ValidatorException(f"Invalid UID '{to_uid}', must match ^[a-z0-9][a-z0-9_]+$")
        
        # Set up string and bytestring versions of each element in long and short form
        from_dn = LDAP_DN % from_uid
        from_dn_enc = from_dn.encode('ascii')
        to_dn = LDAP_DN % to_uid
        to_dn_enc = to_dn.encode('ascii')
        from_uid_enc = from_uid.encode('ascii')
        to_uid_enc = to_uid.encode('ascii')
        
        # Replace long refs: member + owner
        for role in ['member', 'owner']:
            res = self.lc.search_s(LDAP_SUFFIX, ldap.SCOPE_SUBTREE, '%s=%s' % (role, from_dn))
            for entry in res:
                cn = entry[0]
                myhash = entry[1]
                if from_dn_enc in myhash[role]:
                    print("Modifying (long) %s attribute in %s ..." % (role, cn))
                    self.lc.modify_s(cn, [(ldap.MOD_DELETE, role, from_dn_enc)])
                    self.lc.modify_s(cn, [(ldap.MOD_ADD, role, to_dn_enc)])

        # Replace short refs: memberUid
        for role in ['memberUid']:
            res = self.lc.search_s(LDAP_SUFFIX, ldap.SCOPE_SUBTREE, '(&(objectClass=posixGroup)(%s=%s))' % (role, from_uid))
            for entry in res:
                cn = entry[0]
                myhash = entry[1]
                if from_uid_enc in myhash[role]:
                    print("Modifying (short) %s attribute in %s ..." % (role, cn))
                    self.lc.modify_s(cn, [(ldap.MOD_DELETE, role, from_uid_enc)])
                    self.lc.modify_s(cn, [(ldap.MOD_ADD, role, to_uid_enc)])

