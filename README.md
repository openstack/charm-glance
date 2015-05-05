Overview
--------

This charm provides the Glance image service for OpenStack.  It is intended to
be used alongside the other OpenStack components, starting with the Essex
release in Ubuntu 12.04.

Usage
-----

Glance may be deployed in a number of ways.  This charm focuses on 3 main
configurations.  All require the existence of the other core OpenStack
services deployed via Juju charms, specifically: mysql, keystone and
nova-cloud-controller.  The following assumes these services have already
been deployed.

Local Storage
=============

In this configuration, Glance uses the local storage available on the server
to store image data:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller

Swift backed storage
====================

Glance can also use Swift Object storage for image storage.  Swift is often
deployed as part of an OpenStack cloud and provides increased resilience and
scale when compared to using local disk storage.  This configuration assumes
that you have already deployed Swift using the swift-proxy and swift-storage
charms:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller
    juju add-relation glance swift-proxy

This configuration can be used to support Glance in HA/Scale-out deployments.

Ceph backed storage
===================

In this configuration, Glance uses Ceph based object storage to provide
scalable, resilient storage of images.  This configuration assumes that you
have already deployed Ceph using the ceph charm:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller
    juju add-relation glance ceph

This configuration can also be used to support Glance in HA/Scale-out
deployments.

Glance HA/Scale-out
===================

The Glance charm can also be used in a HA/scale-out configuration using
the hacluster charm:

    juju deploy -n 3 glance
    juju deploy hacluster haglance
    juju set glance vip=<virtual IP address to access glance over>
    juju add-relation glance haglance
    juju add-relation glance mysql
    juju add-relation glance keystone
    juju add-relation glance nova-cloud-controller
    juju add-relation glance ceph|swift-proxy

In this configuration, 3 service units host the Glance image service;
API requests are load balanced across all 3 service units via the
configured virtual IP address (which is also registered into Keystone
as the endpoint for Glance).

Note that Glance in this configuration must be used with either Ceph or
Swift providing backing image storage.

Deploying from source
---------------------

The minimum openstack-origin-git config required to deploy from source is:

    openstack-origin-git: include-file://glance-juno.yaml

    glance-juno.yaml
        repositories:
        - {name: requirements,
           repository: 'git://github.com/openstack/requirements',
           branch: stable/juno}
        - {name: glance,
           repository: 'git://github.com/openstack/glance',
           branch: stable/juno}

Note that there are only two 'name' values the charm knows about: 'requirements'
and 'glance'. These repositories must correspond to these 'name' values.
Additionally, the requirements repository must be specified first and the
glance repository must be specified last. All other repostories are installed
in the order in which they are specified.

The following is a full list of current tip repos (may not be up-to-date):

    openstack-origin-git: include-file://glance-master.yaml

    glance-master.yaml
        repositories:
        - {name: requirements,
           repository: 'git://github.com/openstack/requirements',
           branch: master}
        - {name: oslo-concurrency,
           repository: 'git://github.com/openstack/oslo.concurrency',
           branch: master}
        - {name: oslo-config,
           repository: 'git://github.com/openstack/oslo.config',
           branch: master}
        - {name: oslo-db,
           repository: 'git://github.com/openstack/oslo.db',
           branch: master}
        - {name: oslo-i18n,
           repository: 'git://github.com/openstack/oslo.i18n',
           branch: master}
        - {name: oslo-messaging,
           repository: 'git://github.com/openstack/oslo.messaging',
           branch: master}
        - {name: oslo-serialization,
           repository: 'git://github.com/openstack/oslo.serialization',
           branch: master}
        - {name: oslo-utils,
           repository: 'git://github.com/openstack/oslo.utils',
           branch: master}
        - {name: oslo-vmware,
           repository: 'git://github.com/openstack/oslo.vmware',
           branch: master}
        - {name: osprofiler,
           repository: 'git://github.com/stackforge/osprofiler',
           branch: master}
        - {name: pbr,
           repository: 'git://github.com/openstack-dev/pbr',
           branch: master}
        - {name: python-keystoneclient,
           repository: 'git://github.com/openstack/python-keystoneclient',
           branch: master}
        - {name: python-swiftclient,
           repository: 'git://github.com/openstack/python-swiftclient',
           branch: master}
        - {name: sqlalchemy-migrate,
           repository: 'git://github.com/stackforge/sqlalchemy-migrate',
           branch: master}
        - {name: stevedore,
           repository: 'git://github.com/openstack/stevedore',
           branch: master}
        - {name: wsme,
           repository: 'git://github.com/stackforge/wsme',
           branch: master}
        - {name: keystonemiddleware,
           repository: 'git://github.com/openstack/keystonemiddleware',
           branch: master}
        - {name: glance-store,
           repository: 'git://github.com/openstack/glance_store',
           branch: master}
        - {name: glance,
           repository: 'git://github.com/openstack/glance',
           branch: master}

Contact Information
-------------------

Author: Adam Gandelman <adamg@canonical.com>
Report bugs at: http://bugs.launchpad.net/charms
Location: http://jujucharms.com
