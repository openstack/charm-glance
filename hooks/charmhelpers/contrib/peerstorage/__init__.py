from charmhelpers.core.hookenv import (
    relation_ids,
    relation_get,
    local_unit,
    relation_set,
)

"""
This helper provides functions to support use of a peer relation
for basic key/value storage, with the added benefit that all storage
can be replicated across peer units, so this is really useful for
services that issue usernames/passwords to remote services.

def shared_db_changed()
    # Only the lead unit should create passwords
    if not is_leader():
        return
    username = relation_get('username')
    key = '{}.password'.format(username)
    # Attempt to retrieve any existing password for this user
    password = peer_retrieve(key)
    if password is None:
        # New user, create password and store
        password = pwgen(length=64)
        peer_store(key, password)
    create_access(username, password)
    relation_set(password=password)


def cluster_changed()
    # Echo any relation data other that *-address
    # back onto the peer relation so all units have
    # all *.password keys stored on their local relation
    # for later retrieval.
    peer_echo()

"""


def peer_retrieve(key, relation_name='cluster'):
    """ Retrieve a named key from peer relation relation_name """
    cluster_rels = relation_ids(relation_name)
    if len(cluster_rels) > 0:
        cluster_rid = cluster_rels[0]
        return relation_get(attribute=key, rid=cluster_rid,
                            unit=local_unit())
    else:
        raise ValueError('Unable to detect'
                         'peer relation {}'.format(relation_name))


def peer_store(key, value, relation_name='cluster'):
    """ Store the key/value pair on the named peer relation relation_name """
    cluster_rels = relation_ids(relation_name)
    if len(cluster_rels) > 0:
        cluster_rid = cluster_rels[0]
        relation_set(relation_id=cluster_rid,
                     relation_settings={key: value})
    else:
        raise ValueError('Unable to detect '
                         'peer relation {}'.format(relation_name))


def peer_echo(includes=None):
    """Echo filtered attributes back onto the same relation for storage

    Note that this helper must only be called within a peer relation
    changed hook
    """
    rdata = relation_get()
    echo_data = {}
    if includes is None:
        echo_data = rdata.copy()
        for ex in ['private-address', 'public-address']:
            if ex in echo_data:
                echo_data.pop(ex)
    else:
        for attribute, value in rdata.iteritems():
            for include in includes:
                if include in attribute:
                    echo_data[attribute] = value
    if len(echo_data) > 0:
        relation_set(relation_settings=echo_data)
