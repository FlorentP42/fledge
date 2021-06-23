# FLEDGE_BEGIN
# See: http://fledge-iot.readthedocs.io/
# FLEDGE_END

""" Test OMF North Service System tests:
        Tests OMF as a north service along with reconfiguration.
"""

__author__ = "Yash Tatkondawar"
__copyright__ = "Copyright (c) 2021 Dianomic Systems, Inc."

import subprocess
import http.client
import json
import os
import time
import urllib.parse
from pathlib import Path
import pytest
import utils


south_plugin = "sinusoid"
south_asset_name = "sinusoid"
south_service_name="Sine #1"
north_plugin = "OMF"
north_service_name="NorthReadingsToPI_WebAPI"
north_schedule_id=""
filter1_name="SF1"
filter2_name="MD1"
# This  gives the path of directory where fledge is cloned. test_file < packages < python < system < tests < ROOT
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
SCRIPTS_DIR_ROOT = "{}/tests/system/python/scripts/package/".format(PROJECT_ROOT)


@pytest.fixture
def reset_fledge(wait_time):
    try:
        subprocess.run(["cd {} && ./reset"
                       .format(SCRIPTS_DIR_ROOT)], shell=True, check=True)
    except subprocess.CalledProcessError:
        assert False, "reset package script failed!"

    # Wait for fledge server to start
    time.sleep(wait_time)


@pytest.fixture
def start_south_north(clean_setup_fledge_packages, add_south, start_north_pi_server_c_web_api_service, fledge_url, 
                        pi_host, pi_port, pi_admin, pi_passwd):
    global north_schedule_id
    
    add_south(south_plugin, None, fledge_url, service_name="{}".format(south_service_name), installation_type='package')
    
    response = start_north_pi_server_c_web_api_service(fledge_url, pi_host, pi_port, pi_user=pi_admin, pi_pwd=pi_passwd)
    north_schedule_id = response["id"]

    yield start_south_north


@pytest.fixture
def add_configure_filter(add_filter, fledge_url):    
    filter_cfg_scale = {"enable": "true"}
    add_filter("scale", None, filter1_name, filter_cfg_scale, fledge_url, north_service_name, installation_type='package')

    yield add_configure_filter


def verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries):
    get_url = "/fledge/ping"
    ping_result = utils.get_request(fledge_url, get_url)
    assert "dataRead" in ping_result
    assert "dataSent" in ping_result
    assert 0 < ping_result['dataRead'], "South data NOT seen in ping header"
        
    retry_count = 1
    sent = 0
    if not skip_verify_north_interface:
        while retries > retry_count:
            sent = ping_result["dataSent"]
            if sent >= 1:
                break
            else:
                time.sleep(wait_time)

            retry_count += 1
            ping_result = utils.get_request(fledge_url, get_url)

        assert 1 <= sent, "Failed to send data via PI Web API using Basic auth"
    return ping_result


def verify_statistics_map(fledge_url, skip_verify_north_interface):
    get_url = "/fledge/statistics"
    jdoc = utils.get_request(fledge_url, get_url)
    actual_stats_map = utils.serialize_stats_map(jdoc)
    assert 1 <= actual_stats_map[south_asset_name.upper()]
    assert 1 <= actual_stats_map['READINGS']
    if not skip_verify_north_interface:
        assert 1 <= actual_stats_map['Readings Sent']
        assert 1 <= actual_stats_map[north_service_name]


def verify_service_added(fledge_url):
    get_url = "/fledge/south"
    result = utils.get_request(fledge_url, get_url)
    assert len(result["services"])
    assert south_service_name in [s["name"] for s in result["services"]]
    
    get_url = "/fledge/north"
    result = utils.get_request(fledge_url, get_url)
    assert len(result)
    assert north_service_name in [s["name"] for s in result]
    
    get_url = "/fledge/service"
    result = utils.get_request(fledge_url, get_url)
    assert len(result["services"])
    assert south_service_name in [s["name"] for s in result["services"]]
    assert north_service_name in [s["name"] for s in result["services"]]


def verify_filter_added(fledge_url):
    get_url = "/fledge/filter"
    result = utils.get_request(fledge_url, get_url)
    assert len(result["filters"])
    assert filter1_name in [s["name"] for s in result["filters"]]
    return result


def verify_asset(fledge_url):
    get_url = "/fledge/asset"
    result = utils.get_request(fledge_url, get_url)
    assert len(result), "No asset found"
    assert south_asset_name in [s["assetCode"] for s in result]


def verify_asset_tracking_details(fledge_url):
    tracking_details = utils.get_asset_tracking_details(fledge_url, "Ingest")
    assert len(tracking_details["track"]), "Failed to track Ingest event"
    tracked_item = tracking_details["track"][0]
    assert south_service_name == tracked_item["service"]
    assert south_asset_name == tracked_item["asset"]
    assert south_asset_name == tracked_item["plugin"]

    egress_tracking_details = utils.get_asset_tracking_details(fledge_url, "Egress")
    assert len(egress_tracking_details["track"]), "Failed to track Egress event"
    tracked_item = egress_tracking_details["track"][0]
    assert north_service_name == tracked_item["service"]
    assert south_asset_name == tracked_item["asset"]
    assert north_plugin == tracked_item["plugin"]


class TestOMFNorthService:
    def test_omf_service_with_restart(self, reset_fledge, start_south_north, skip_verify_north_interface, fledge_url, wait_time, retries):
        """ Test OMF as a North service before and after restarting fledge.
            remove_and_add_pkgs: Fixture to remove and install latest fledge packages
            reset_fledge: Fixture to reset fledge
            start_south_north: Adds and configures south(sinusoid) and north(OMF) service
            Assertions:
                on endpoint GET /fledge/south
                on endpoint GET /fledge/ping
                on endpoint GET /fledge/asset"""        
        
        # Wait until south and north services are created
        time.sleep(wait_time)
        
        verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)        
        verify_asset(fledge_url)
        verify_service_added(fledge_url)        
        verify_statistics_map(fledge_url, skip_verify_north_interface)

        put_url = "/fledge/restart"
        utils.put_request(fledge_url, urllib.parse.quote(put_url))
        
        # Wait for fledge to restart
        time.sleep(wait_time * 2)

        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after restart
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] < new_ping_result['dataSent']

    def test_omf_service_with_enable_disable(self, reset_fledge, start_south_north, skip_verify_north_interface, fledge_url, wait_time, retries):
        """ Test OMF as a North service by enabling and disabling it.
            remove_and_add_pkgs: Fixture to remove and install latest fledge packages
            reset_fledge: Fixture to reset fledge
            start_south_north: Adds and configures south(sinusoid) and north(OMF) service
            Assertions:
                on endpoint GET /fledge/south
                on endpoint GET /fledge/ping
                on endpoint GET /fledge/asset"""                
        
        # Wait until south and north services are created
        time.sleep(wait_time)
        
        verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)        
        verify_asset(fledge_url)
        verify_service_added(fledge_url)        
        verify_statistics_map(fledge_url, skip_verify_north_interface)
        
        data = {"enabled": "false"}
        put_url = "/fledge/schedule/{}".format(north_schedule_id)
        resp = utils.put_request(fledge_url, urllib.parse.quote(put_url), data)
        assert False == resp['schedule']['enabled']
        
        # Wait for service to disable
        time.sleep(wait_time)        
        
        data = {"enabled": "true"}
        put_url = "/fledge/schedule/{}".format(north_schedule_id)
        resp = utils.put_request(fledge_url, urllib.parse.quote(put_url), data)
        assert True == resp['schedule']['enabled']
        
        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after disable/enable
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] < new_ping_result['dataSent']


    def test_omf_service_with_delete_add(self, reset_fledge, start_south_north, start_north_pi_server_c_web_api_service, skip_verify_north_interface, fledge_url, wait_time, retries, pi_host, pi_port, pi_admin, pi_passwd):
        """ Test OMF as a North service by deleting and adding north service.
            remove_and_add_pkgs: Fixture to remove and install latest fledge packages
            reset_fledge: Fixture to reset fledge
            start_south_north: Adds and configures south(sinusoid) and north(OMF) service
            Assertions:
                on endpoint GET /fledge/south
                on endpoint GET /fledge/ping
                on endpoint GET /fledge/asset"""               
        
        global north_schedule_id
        
        # Wait until south and north services are created
        time.sleep(wait_time)
        
        verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)        
        verify_asset(fledge_url)
        verify_service_added(fledge_url)        
        verify_statistics_map(fledge_url, skip_verify_north_interface)
        
        delete_url = "/fledge/service/{}".format(north_service_name)
        resp = utils.delete_request(fledge_url, delete_url)
        assert "Service {} deleted successfully.".format(north_service_name) == resp['result']
        
        # Wait for service to get deleted
        time.sleep(wait_time)
    
        response = start_north_pi_server_c_web_api_service(fledge_url, pi_host, pi_port, pi_user=pi_admin, pi_pwd=pi_passwd)
        north_schedule_id = response["id"]
        
        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after delete/add of north service
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] < new_ping_result['dataSent']

    def test_omf_service_with_reconfig(self, reset_fledge, start_south_north, skip_verify_north_interface, fledge_url, wait_time, retries):
        """ Test OMF as a North service by reconfiguring it.
            remove_and_add_pkgs: Fixture to remove and install latest fledge packages
            reset_fledge: Fixture to reset fledge
            start_south_north: Adds and configures south(sinusoid) and north(OMF) service
            Assertions:
                on endpoint GET /fledge/south
                on endpoint GET /fledge/ping
                on endpoint GET /fledge/asset"""                
        
        # Wait until south and north services are created
        time.sleep(wait_time)
        
        verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)        
        verify_asset(fledge_url)
        verify_service_added(fledge_url)        
        verify_statistics_map(fledge_url, skip_verify_north_interface)
        
        # Good reconfiguration to check data is not sent
        data = {"SendFullStructure": "false"}
        put_url = "/fledge/category/{}".format(north_service_name)
        resp = utils.put_request(fledge_url, urllib.parse.quote(put_url), data)
        assert "false" == resp["SendFullStructure"]["value"]
        
        # Wait for service reconfiguration
        time.sleep(wait_time)        
        
        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after delete/add of north service
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] < new_ping_result['dataSent']
        
        # Bad reconfiguration to check data is not sent
        data = {"PIWebAPIUserId": "Admin"}
        put_url = "/fledge/category/{}".format(north_service_name)
        resp = utils.put_request(fledge_url, urllib.parse.quote(put_url), data)
        assert "Admin" == resp["PIWebAPIUserId"]["value"]
        
        # Wait for service reconfiguration
        time.sleep(wait_time)        
        
        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after delete/add of north service
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] == new_ping_result['dataSent']


class TestOMFNorthServicewithFilters:
    def test_omf_service_with_filter(self, reset_fledge, start_south_north, add_configure_filter, skip_verify_north_interface, fledge_url, wait_time, retries):
        """ Test OMF as a North service with filters.
            remove_and_add_pkgs: Fixture to remove and install latest fledge packages
            reset_fledge: Fixture to reset fledge
            start_south_north: Adds and configures south(sinusoid) and north(OMF) service
            Assertions:
                on endpoint GET /fledge/south
                on endpoint GET /fledge/ping
                on endpoint GET /fledge/asset"""        
        
        # Wait until south and north services are created
        time.sleep(wait_time)
        
        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)        
        verify_asset(fledge_url)
        verify_service_added(fledge_url)
        verify_filter_added(fledge_url)        
        verify_statistics_map(fledge_url, skip_verify_north_interface)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after delete/add of north service
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] < new_ping_result['dataSent']
        
    def test_omf_service_with_disable_enable_filter(self, reset_fledge, start_south_north, add_configure_filter, skip_verify_north_interface, fledge_url, wait_time, retries):
        """ Test OMF as a North service with enable/diable of filters.
            remove_and_add_pkgs: Fixture to remove and install latest fledge packages
            reset_fledge: Fixture to reset fledge
            start_south_north: Adds and configures south(sinusoid) and north(OMF) service
            Assertions:
                on endpoint GET /fledge/south
                on endpoint GET /fledge/ping
                on endpoint GET /fledge/asset"""        
        
        # Wait until south and north services are created
        time.sleep(wait_time)
        
        verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)        
        verify_asset(fledge_url)
        verify_service_added(fledge_url)
        verify_filter_added(fledge_url)    
        verify_statistics_map(fledge_url, skip_verify_north_interface)
        
        data = {"enable": "false"}
        put_url = "/fledge/category/{}_SF1".format(north_service_name)
        resp = utils.put_request(fledge_url, urllib.parse.quote(put_url), data)
        assert "false" == resp['enable']['value']
        
        # Wait for service to disable
        time.sleep(wait_time)        
        
        data = {"enable": "true"}
        put_url = "/fledge/category/{}_SF1".format(north_service_name)
        resp = utils.put_request(fledge_url, urllib.parse.quote(put_url), data)
        assert "true" == resp['enable']['value']
        
        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after disable/enable
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] < new_ping_result['dataSent']
        
    def test_omf_service_with_filter_reconfig(self, reset_fledge, start_south_north, add_configure_filter, skip_verify_north_interface, fledge_url, wait_time, retries):
        """ Test OMF as a North service with reconfiguration of filters.
            remove_and_add_pkgs: Fixture to remove and install latest fledge packages
            reset_fledge: Fixture to reset fledge
            start_south_north: Adds and configures south(sinusoid) and north(OMF) service
            Assertions:
                on endpoint GET /fledge/south
                on endpoint GET /fledge/ping
                on endpoint GET /fledge/asset"""        
        
        # Wait until south and north services are created
        time.sleep(wait_time)
        
        verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)        
        verify_asset(fledge_url)
        verify_service_added(fledge_url)
        verify_filter_added(fledge_url)      
        verify_statistics_map(fledge_url, skip_verify_north_interface)
        
        data = {"factor": "50"}
        put_url = "/fledge/category/{}_SF1".format(north_service_name)
        resp = utils.put_request(fledge_url, urllib.parse.quote(put_url), data)
        assert "50.0" == resp['factor']['value']
        
        # Wait for filter reconfiguration
        time.sleep(wait_time)        
        
        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after disable/enable
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] < new_ping_result['dataSent']
        
    @pytest.mark.skip(reason="FOGL-5215: Deleting a service doesn't delete its filter categories")
    def test_omf_service_with_delete_add(self, reset_fledge, start_south_north, add_configure_filter, add_filter, start_north_pi_server_c_web_api_service, skip_verify_north_interface, fledge_url, wait_time, retries, pi_host, pi_port, pi_admin, pi_passwd):
        """ Test OMF as a North service by deleting and adding north service.
            remove_and_add_pkgs: Fixture to remove and install latest fledge packages
            reset_fledge: Fixture to reset fledge
            start_south_north: Adds and configures south(sinusoid) and north(OMF) service
            Assertions:
                on endpoint GET /fledge/south
                on endpoint GET /fledge/ping
                on endpoint GET /fledge/asset"""               
        
        global north_schedule_id
        
        # Wait until south and north services are created
        time.sleep(wait_time)
        
        verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)        
        verify_asset(fledge_url)
        verify_service_added(fledge_url)      
        verify_filter_added(fledge_url)  
        verify_statistics_map(fledge_url, skip_verify_north_interface)
        
        delete_url = "/fledge/service/{}".format(north_service_name)
        resp = utils.delete_request(fledge_url, delete_url)
        assert "Service {} deleted successfully.".format(north_service_name) == resp['result']
        
        # Wait for service to get deleted
        time.sleep(wait_time)
    
        response = start_north_pi_server_c_web_api_service(fledge_url, pi_host, pi_port, pi_user=pi_admin, pi_pwd=pi_passwd)
        north_schedule_id = response["id"]
        
        filter_cfg_scale = {"enable": "true"}
        add_filter("scale", None, "SF2", filter_cfg_scale, fledge_url, north_service_name, installation_type='package')
        
        # Wait for service and filter to get added
        time.sleep(wait_time)
        
        verify_service_added(fledge_url)      
        verify_filter_added(fledge_url)
        
        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after delete/add of north service
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] < new_ping_result['dataSent']
        
    
    def test_omf_service_with_delete_add_filter(self, reset_fledge, start_south_north, add_configure_filter, add_filter, skip_verify_north_interface, fledge_url, wait_time, retries, pi_host, pi_port, pi_admin, pi_passwd):
        """ Test OMF as a North service by deleting and adding north service.
            remove_and_add_pkgs: Fixture to remove and install latest fledge packages
            reset_fledge: Fixture to reset fledge
            start_south_north: Adds and configures south(sinusoid) and north(OMF) service
            Assertions:
                on endpoint GET /fledge/south
                on endpoint GET /fledge/ping
                on endpoint GET /fledge/asset"""       
        
        # Wait until south and north services are created
        time.sleep(wait_time)
        
        verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)        
        verify_asset(fledge_url)
        verify_service_added(fledge_url)      
        verify_filter_added(fledge_url)  
        verify_statistics_map(fledge_url, skip_verify_north_interface)
        
        data = {"pipeline": []}
        put_url = "/fledge/filter/{}/pipeline?allow_duplicates=true&append_filter=false" \
            .format(north_service_name)
        resp = utils.put_request(fledge_url, urllib.parse.quote(put_url, safe='?,=,&,/'), data)
        
        delete_url = "/fledge/filter/{}".format(filter1_name)
        resp = utils.delete_request(fledge_url, delete_url)
        assert "Filter {} deleted successfully".format(filter1_name) == resp['result']
        
        # Wait for service to get deleted
        time.sleep(wait_time)
        
        filter_cfg_scale = {"enable": "true"}
        add_filter("scale", None, filter1_name, filter_cfg_scale, fledge_url, north_service_name, installation_type='package')
        
        # Wait for filter to get added
        time.sleep(wait_time)
      
        verify_filter_added(fledge_url)
        
        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after delete/add of north service
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] < new_ping_result['dataSent']
        
    def test_omf_service_with_filter_reorder(self, reset_fledge, start_south_north, add_configure_filter, add_filter, skip_verify_north_interface, fledge_url, wait_time, retries, pi_host, pi_port, pi_admin, pi_passwd):
        """ Test OMF as a North service by deleting and adding north service.
            remove_and_add_pkgs: Fixture to remove and install latest fledge packages
            reset_fledge: Fixture to reset fledge
            start_south_north: Adds and configures south(sinusoid) and north(OMF) service
            Assertions:
                on endpoint GET /fledge/south
                on endpoint GET /fledge/ping
                on endpoint GET /fledge/asset"""       
        
        # Wait until south and north services are created
        time.sleep(wait_time)
        
        verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)        
        verify_asset(fledge_url)
        verify_service_added(fledge_url)      
        verify_filter_added(fledge_url)  
        verify_statistics_map(fledge_url, skip_verify_north_interface)  

        # Adding second filter
        filter_cfg_meta = {"enable": "true"}
        resp = add_filter("metadata", None, filter2_name, filter_cfg_meta, fledge_url, north_service_name, installation_type='package')
        
        # Wait for filter to get added
        time.sleep(wait_time)
      
        result = verify_filter_added(fledge_url)
        assert filter2_name in [s["name"] for s in result["filters"]]
        
        # Verify the filter pipeline order
        get_url = "/fledge/filter/{}/pipeline".format(north_service_name)
        resp = utils.get_request(fledge_url, get_url)
        assert filter1_name == resp['result']['pipeline'][0]
        assert filter2_name == resp['result']['pipeline'][1]
        
        data = {"pipeline": ["{}".format(filter2_name), "{}".format(filter1_name)]}
        put_url = "/fledge/filter/{}/pipeline?allow_duplicates=true&append_filter=false" \
            .format(north_service_name)
        resp = utils.put_request(fledge_url, urllib.parse.quote(put_url, safe='?,=,&,/'), data)
        
        # Verify the filter pipeline order
        get_url = "/fledge/filter/{}/pipeline".format(north_service_name)
        resp = utils.get_request(fledge_url, get_url)
        assert filter2_name == resp['result']['pipeline'][0]
        assert filter1_name == resp['result']['pipeline'][1]
        
        old_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        
        # Wait for read and sent readings to increase
        time.sleep(wait_time)
        
        new_ping_result = verify_ping(fledge_url, skip_verify_north_interface, wait_time, retries)
        # Verifies whether Read and Sent readings are increasing after reordering of filters
        assert old_ping_result['dataRead'] < new_ping_result['dataRead']
        assert old_ping_result['dataSent'] < new_ping_result['dataSent']