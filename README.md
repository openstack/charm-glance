# Overview

The glance charm deploys [Glance][upstream-glance], the core OpenStack service
that acts as the central repository for virtual machine (VM) images. The charm
works alongside other Juju-deployed OpenStack services.

# Usage

## Configuration

This section covers common and/or important configuration options. See file
`config.yaml` for the full list of options, along with their descriptions and
default values. See the [Juju documentation][juju-docs-config-apps] for details
on configuring applications.

#### `openstack-origin`

The `openstack-origin` option states the software sources. A common value is an
OpenStack UCA release (e.g. 'cloud:bionic-ussuri' or 'cloud:focal-victoria').
See [Ubuntu Cloud Archive][wiki-uca]. The underlying host's existing apt
sources will be used if this option is not specified (this behaviour can be
explicitly chosen by using the value of 'distro').

#### `pool-type`

The `pool-type` option dictates the Ceph storage pool type. See sections 'Ceph
pool type' and 'Ceph backed storage' for more information.

## Deployment

This section includes four different deployment scenarios (with their
respective backends). Each scenario requires these applications to be present:
keystone, nova-cloud-controller, nova-compute, and a cloud database.

> **Note**: The database application is determined by the series. Prior to focal
  [percona-cluster][percona-cluster-charm] is used, otherwise it is
  [mysql-innodb-cluster][mysql-innodb-cluster-charm]. In the example
  deployments below mysql-innodb-cluster has been chosen.

### Ceph-backed storage

Ceph is the recommended storage backend solution for Glance. The steps below
assume a pre-existing Ceph cluster (see the [ceph-mon][ceph-mon-charm] and
[ceph-osd][ceph-osd-charm] charms).

Here, Glance is deployed to a new container on machine '1' and related to the
Ceph cluster via the ceph-mon charm:

    juju deploy --to lxd:1 glance
    juju add-relation glance:ceph ceph-mon:client

Proceed with a group of commands common to all three scenarios:

    juju add-relation glance:identity-service keystone:identity-service
    juju add-relation glance:image-service nova-cloud-controller:image-service
    juju add-relation glance:image-service nova-compute:image-service

    juju deploy mysql-router glance-mysql-router
    juju add-relation glance-mysql-router:db-router mysql-innodb-cluster:db-router
    juju add-relation glance-mysql-router:shared-db glance:shared-db

This configuration can be used to support Glance in HA/scale-out deployments.

> **Note**: In this scenario Glance acts as a Ceph client, which requires
  L3 network connectivity to Ceph monitors and OSDs. For MAAS-based deployments
  this can be addressed with network spaces (see section 'Network spaces'
  below).

### Object storage-backed storage

Glance can use Object storage as its storage backend. OpenStack Swift and Ceph
RADOS Gateway are supported, and both resulting configurations can be used to
support Glance in HA/scale-out deployments.

#### Swift

The steps below assume a pre-existing Swift deployment (see the
[swift-proxy][swift-proxy-charm] and [swift-storage][swift-storage-charm]
charms).

Here, Glance is deployed to a new container on machine '1' and related to Swift
via the swift-proxy charm:

    juju deploy --to lxd:1 glance
    juju add-relation glance:object-store swift-proxy:object-store

Proceed with the common group of commands from the Ceph scenario.

#### Ceph RADOS Gateway

The steps below assume a pre-existing Ceph RADOS Gateway deployment (see the
[ceph-radosgw][ceph-radosgw-charm]).

Here, Glance is deployed to a new container on machine '1' and related to the
ceph-radosgw application:

    juju deploy --to lxd:1 glance
    juju add-relation glance:object-store ceph-radosgw:object-store

Proceed with the common group of commands from the Ceph scenario.

### Local storage

Glance can simply use the storage available on the application unit's machine
to store image data. Here, Glance is deployed to a new container on machine
'1':

    juju deploy --to lxd:1 glance

Proceed with the common group of commands from the Ceph scenario.

## Multiple backends

If multiple storage backends are configured the cloud operator can specify, at
image upload time, which backend will be used to store the image. This is done
by using the `--store` option to the `glance` CLI client:

    glance image-create --store <backend-name> ...

Otherwise, the default backend is determined by the following precedence order
of backend names: 'ceph', 'swift', and then 'local'.

> **Important**: The backend name of 'swift' denotes both object storage
  solutions (i.e. Swift and Ceph RADOS Gateway).

## Actions

This section covers Juju [actions][juju-docs-actions] supported by the charm.
Actions allow specific operations to be performed on a per-unit basis. To
display action descriptions run `juju actions glance`. If the charm is not
deployed then see file `actions.yaml`.

* `openstack-upgrade`
* `pause`
* `resume`
* `security-checklist`

## Ceph pool type

Ceph storage pools can be configured to ensure data resiliency either through
replication or by erasure coding. This charm supports both types via the
`pool-type` configuration option, which can take on the values of 'replicated'
and 'erasure-coded'. The default value is 'replicated'.

For this charm, the pool type will be associated with Glance images.

> **Note**: Erasure-coded pools are supported starting with Ceph Luminous.

### Replicated pools

Replicated pools use a simple replication strategy in which each written object
is copied, in full, to multiple OSDs within the cluster.

The `ceph-osd-replication-count` option sets the replica count for any object
stored within the 'glance' rbd pool. Increasing this value increases data
resilience at the cost of consuming more real storage in the Ceph cluster. The
default value is '3'.

> **Important**: The `ceph-osd-replication-count` option must be set prior to
  adding the relation to the ceph-mon (or ceph-proxy) application. Otherwise,
  the pool's configuration will need to be set by interfacing with the cluster
  directly.

### Erasure coded pools

Erasure coded pools use a technique that allows for the same resiliency as
replicated pools, yet reduces the amount of space required. Written data is
split into data chunks and error correction chunks, which are both distributed
throughout the cluster.

> **Note**: Erasure coded pools require more memory and CPU cycles than
  replicated pools do.

When using erasure coded pools for Glance images two pools will be created: a
replicated pool (for storing RBD metadata) and an erasure coded pool (for
storing the data written into the RBD). The `ceph-osd-replication-count`
configuration option only applies to the metadata (replicated) pool.

Erasure coded pools can be configured via options whose names begin with the
`ec-` prefix.

> **Important**: It is strongly recommended to tailor the `ec-profile-k` and
  `ec-profile-m` options to the needs of the given environment. These latter
  options have default values of '1' and '2' respectively, which result in the
  same space requirements as those of a replicated pool.

See [Ceph Erasure Coding][cdg-ceph-erasure-coding] in the [OpenStack Charms
Deployment Guide][cdg] for more information.

## Ceph BlueStore compression

This charm supports [BlueStore inline compression][ceph-bluestore-compression]
for its associated Ceph storage pool(s). The feature is enabled by assigning a
compression mode via the `bluestore-compression-mode` configuration option. The
default behaviour is to disable compression.

The efficiency of compression depends heavily on what type of data is stored
in the pool and the charm provides a set of configuration options to fine tune
the compression behaviour.

> **Note**: BlueStore compression is supported starting with Ceph Mimic.

## High availability

When more than one unit is deployed with the [hacluster][hacluster-charm]
application the charm will bring up an HA active/active cluster.

There are two mutually exclusive high availability options: using virtual IP(s)
or DNS. In both cases the hacluster subordinate charm is used to provide the
Corosync and Pacemaker backend HA functionality.

See [OpenStack high availability][cdg-ha-apps] in the [OpenStack Charms
Deployment Guide][cdg] for details.

> **Important**: Glance in an HA configuration must be backed by either Ceph or
  Swift.

## Glance metering

Glance metering can be achieved with Ceilometer. The
[rabbitmq-server][rabbitmq-server-charm] and
[ceilometer-agent][ceilometer-agent-charm] applications are required to be
present.

Assuming Glance is deployed, add two relations:

    juju add-relation glance:amqp rabbitmq-server:amqp
    juju add-relation glance:amqp ceilometer-agent:amqp
    juju add-relation glance:juju-info ceilometer-agent:container

## Network spaces

This charm supports the use of Juju [network spaces][juju-docs-spaces]. This
feature optionally allows specific types of the application's network traffic
to be bound to subnets that the underlying hardware is connected to.

> **Note**: Spaces must be configured in the backing cloud prior to deployment.

API endpoints can be bound to distinct network spaces supporting the network
separation of public, internal and admin endpoints.

Glance acts as a Ceph client and needs IP connectivity to Ceph monitors and
OSDs. Binding the ceph endpoint to a space can solve this problem in case
monitors and OSDs are located on a single L2 broadcast domain (if they are not,
static or dynamic routes need to be used in addition to spaces).

Access to the underlying MySQL instance can also be bound to a specific space
using the shared-db relation.

To use this feature, use the --bind option when deploying the charm:

    juju deploy glance --bind \
       "public=public-space \
        internal=internal-space \
        admin=admin-space \
        shared-db=internal-space \
        ceph=ceph-access-space"

Alternatively, these can also be provided as part of a juju native bundle
configuration:

```yaml
    glance:
      charm: cs:xenial/glance
      num_units: 1
      bindings:
        public: public-space
        admin: admin-space
        internal: internal-space
        shared-db: internal-space
        ceph: ceph-access-space
```

> **Note**: Existing glance units configured with the `os-admin-network`,
  `os-internal-network`, or `os-public-network` options will continue to honour
  them. Furthermore, these options override any space bindings, if set.

## Policy overrides

Policy overrides is an advanced feature that allows an operator to override the
default policy of an OpenStack service. The policies that the service supports,
the defaults it implements in its code, and the defaults that a charm may
include should all be clearly understood before proceeding.

> **Caution**: It is possible to break the system (for tenants and other
  services) if policies are incorrectly applied to the service.

Policy statements are placed in a YAML file. This file (or files) is then (ZIP)
compressed into a single file and used as an application resource. The override
is then enabled via a Boolean charm option.

Here are the essential commands (filenames are arbitrary):

    zip overrides.zip override-file.yaml
    juju attach-resource glance policyd-override=overrides.zip
    juju config glance use-policyd-override=true

See [Policy overrides][cdg-appendix-n] in the [OpenStack Charms Deployment
Guide][cdg] for a thorough treatment of this feature.

# Bugs

Please report bugs on [Launchpad][lp-bugs-charm-glance].

For general charm questions refer to the [OpenStack Charm Guide][cg].

<!-- LINKS -->

[cg]: https://docs.openstack.org/charm-guide
[cdg]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide
[cdg-appendix-n]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-policy-overrides.html
[lp-bugs-charm-glance]: https://bugs.launchpad.net/charm-glance/+filebug
[hacluster-charm]: https://jaas.ai/hacluster
[ceph-mon-charm]: https://jaas.ai/ceph-mon
[ceph-osd-charm]: https://jaas.ai/ceph-osd
[ceph-radosgw-charm]: https://jaas.ai/ceph-radosgw
[swift-proxy-charm]: https://jaas.ai/swift-proxy
[swift-storage-charm]: https://jaas.ai/swift-storage
[percona-cluster-charm]: https://jaas.ai/percona-cluster
[mysql-innodb-cluster-charm]: https://jaas.ai/mysql-innodb-cluster
[rabbitmq-server-charm]: https://jaas.ai/rabbitmq-server
[ceilometer-agent-charm]: https://jaas.ai/ceilometer-agent
[cdg-ha-apps]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-ha.html#ha-applications
[juju-docs-spaces]: https://juju.is/docs/spaces
[wiki-uca]: https://wiki.ubuntu.com/OpenStack/CloudArchive
[juju-docs-config-apps]: https://juju.is/docs/configuring-applications
[cdg-ceph-erasure-coding]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-erasure-coding.html
[ceph-bluestore-compression]: https://docs.ceph.com/en/latest/rados/configuration/bluestore-config-ref/#inline-compression
[upstream-glance]: https://docs.openstack.org/glance/latest/
[juju-docs-actions]: https://jaas.ai/docs/actions
