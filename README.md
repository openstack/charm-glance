# Overview

The glance charm provides the Glance image service for OpenStack. It is
intended to be used alongside the other OpenStack components.

# Usage

Glance may be deployed in a number of ways. This charm focuses on 3 main
configurations. All require the existence of the other core OpenStack services
deployed via Juju charms, specifically: mysql, keystone and
nova-cloud-controller. The following assumes these services have already been
deployed.

## Configuration

This section covers common and/or important configuration options. See file
`config.yaml` for the full list of options, along with their descriptions and
default values. See the [Juju documentation][juju-docs-config-apps] for details
on configuring applications.

#### `openstack-origin`

The `openstack-origin` option states the software sources. A common value is an
OpenStack UCA release (e.g. 'cloud:xenial-queens' or 'cloud:bionic-ussuri').
See [Ubuntu Cloud Archive][wiki-uca]. The underlying host's existing apt
sources will be used if this option is not specified (this behaviour can be
explicitly chosen by using the value of 'distro').

#### `pool-type`

The `pool-type` option dictates the Ceph storage pool type. See sections 'Ceph
pool type' and 'Ceph backed storage' for more information.

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

## Local Storage

In this configuration, Glance uses the local storage available on the server
to store image data:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller

## Swift backed storage

Glance can also use Swift Object storage for image storage. Swift is often
deployed as part of an OpenStack cloud and provides increased resilience and
scale when compared to using local disk storage. This configuration assumes
that you have already deployed Swift using the swift-proxy and swift-storage
charms:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller
    juju add-relation glance swift-proxy

This configuration can be used to support Glance in HA/Scale-out deployments.

## Ceph backed storage

In this configuration, Glance uses Ceph based object storage to provide
scalable, resilient storage of images. This configuration assumes that you
have already deployed Ceph using the ceph charm:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller
    juju add-relation glance ceph-mon

This configuration can also be used to support Glance in HA/Scale-out
deployments.

> **Note**: Glance acts as a Ceph client in this case which requires IP (L3)
  connectivity to Ceph monitors and OSDs. For MAAS-based deployments this can
  be addressed with network spaces (see section 'Network spaces' below).

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

In order to do Glance metering with Ceilometer, an AMQP relation is required
e.g.

    juju deploy glance
    juju deploy rabbitmq-server
    juju deploy ceilometer-agent
    ...
    juju add-relation glance rabbitmq-server
    juju add-relation glance ceilometer-agent
    ...

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

See appendix [Policy overrides][cdg-appendix-n] in the [OpenStack Charms
Deployment Guide][cdg] for a thorough treatment of this feature.

# Bugs

Please report bugs on [Launchpad][lp-bugs-charm-glance].

For general charm questions refer to the [OpenStack Charm Guide][cg].

<!-- LINKS -->

[cg]: https://docs.openstack.org/charm-guide
[cdg]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide
[cdg-appendix-n]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-policy-overrides.html
[lp-bugs-charm-glance]: https://bugs.launchpad.net/charm-glance/+filebug
[hacluster-charm]: https://jaas.ai/hacluster
[cdg-ha-apps]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-ha.html#ha-applications
[juju-docs-spaces]: https://juju.is/docs/spaces
[wiki-uca]: https://wiki.ubuntu.com/OpenStack/CloudArchive
[juju-docs-config-apps]: https://juju.is/docs/configuring-applications
[cdg-ceph-erasure-coding]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-erasure-coding.html
[ceph-bluestore-compression]: https://docs.ceph.com/en/latest/rados/configuration/bluestore-config-ref/#inline-compression
