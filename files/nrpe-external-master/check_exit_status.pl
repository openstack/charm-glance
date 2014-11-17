#!/usr/bin/perl
################################################################################
#                                                                              #
#  Copyright (C) 2011 Chad Columbus <ccolumbu@hotmail.com>                     #
#                                                                              #
#   This program is free software; you can redistribute it and/or modify       #
#   it under the terms of the GNU General Public License as published by       #
#   the Free Software Foundation; either version 2 of the License, or          #
#   (at your option) any later version.                                        #
#                                                                              #
#   This program is distributed in the hope that it will be useful,            #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of             #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the              #
#   GNU General Public License for more details.                               #
#                                                                              #
#   You should have received a copy of the GNU General Public License          #
#   along with this program; if not, write to the Free Software                #
#   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA  #
#                                                                              #
################################################################################

use strict;
use Getopt::Std;
$| = 1;

my %opts;
getopts('heronp:s:', \%opts);

my $VERSION = "Version 1.0";
my $AUTHOR = '(c) 2011 Chad Columbus <ccolumbu@hotmail.com>';

# Default values:
my $script_to_check;
my $pattern = 'is running';
my $cmd;
my $message;
my $error;

# Exit codes
my $STATE_OK = 0;
my $STATE_WARNING = 1;
my $STATE_CRITICAL = 2;
my $STATE_UNKNOWN = 3;

# Parse command line options
if ($opts{'h'} || scalar(%opts) == 0) {
	&print_help();
	exit($STATE_OK);
}

# Make sure scipt is provided:
if ($opts{'s'} eq '') {
	# Script to run not provided
	print "\nYou must provide a script to run. Example: -s /etc/init.d/httpd\n";
	exit($STATE_UNKNOWN);
} else {
	$script_to_check = $opts{'s'};
}

# Make sure only a-z, 0-9, /, _, and - are used in the script.
if ($script_to_check =~ /[^a-z0-9\_\-\/\.]/) {
	# Script contains illegal characters exit.
	print "\nScript to check can only contain Letters, Numbers, Periods, Underscores, Hyphens, and/or Slashes\n";
	exit($STATE_UNKNOWN);
}

# See if script is executable
if (! -x "$script_to_check") {
	print "\nIt appears you can't execute $script_to_check, $!\n";
	exit($STATE_UNKNOWN);
}

# If a pattern is provided use it:
if ($opts{'p'} ne '') {
	$pattern = $opts{'p'};
}

# If -r run command via sudo as root:
if ($opts{'r'}) {
	$cmd = "sudo -n $script_to_check status" . ' 2>&1';
} else {
	$cmd = "$script_to_check status" . ' 2>&1';
}

my $cmd_result = `$cmd`;
chomp($cmd_result);
if ($cmd_result =~ /sudo/i) {
	# This means it could not run the sudo command
	$message = "$script_to_check CRITICAL - Could not run: 'sudo -n $script_to_check status'. Result is $cmd_result";
	$error = $STATE_UNKNOWN;
} else {
	# Check exitstatus instead of output:
	if ($opts{'e'} == 1) {
		if ($? != 0) {
			# error
			$message = "$script_to_check CRITICAL - Exit code: $?\.";
			if ($opts{'o'} == 0) {
				$message .= " $cmd_result";
			}
			$error = $STATE_CRITICAL;
		} else {
			# success
			$message = "$script_to_check OK - Exit code: $?\.";
			if ($opts{'o'} == 0) {
				$message .= " $cmd_result";
			}
			$error = $STATE_OK;
		}
	} else {
		my $not_check = 1;
		if ($opts{'n'} == 1) { 
			$not_check = 0;
		}
		if (($cmd_result =~ /$pattern/i) == $not_check) {
			$message = "$script_to_check OK";
			if ($opts{'o'} == 0) {
				$message .= " - $cmd_result";
			}
			$error = $STATE_OK;
		} else {
			$message = "$script_to_check CRITICAL";
			if ($opts{'o'} == 0) {
				$message .= " - $cmd_result";
			}
			$error = $STATE_CRITICAL;
		}
	}
}

if ($message eq '') {
	print "Error: program failed in an unknown way\n";
	exit($STATE_UNKNOWN);
}

if ($error) {
	print "$message\n";
	exit($error);
} else {
	# If we get here we are OK
	print "$message\n";
	exit($STATE_OK);
}

####################################
# Start Subs:
####################################
sub print_help() {
        print << "EOF";
Check the output or exit status of a script.
$VERSION
$AUTHOR

Options:
-h
	Print detailed help screen

-s
	'FULL PATH TO SCRIPT' (required)
	This is the script to run, the script is designed to run scripts in the
	/etc/init.d dir (but can run any script) and will call the script with 
	a 'status' argument. So if you use another script make sure it will
	work with /path/script status, example: /etc/init.d/httpd status 

-e
	This is the "exitstaus" flag, it means check the exit status 
	code instead of looking for a pattern in the output of the script.

-p 'REGEX'
	This is a pattern to look for in the output of the script to confirm it
	is running, default is 'is running', but not all init.d scripts output 
	(iptables), so you can specify an arbitrary pattern.
	All patterns are case insensitive.

-n 
	This is the "NOT" flag, it means not the -p pattern, so if you want to
	make sure the output of the script does NOT contain -p 'REGEX'

-r
	This is the "ROOT" flag, it means run as root via sudo. You will need a 
	line in your /etc/sudoers file like:
	nagios ALL=(root) NOPASSWD: /etc/init.d/* status

-o
	This is the "SUPPRESS OUTPUT" flag. Some programs have a long output
	(like iptables), this flag suppresses that output so it is not printed
	as a part of the nagios message.
EOF
}

