"""Exercise collection failures without systemd, interfaces or production files."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'metrics.sh'


class Metrics(unittest.TestCase):
    def collect(self, *, failed='', systemd_status='0', peers='peerbase64= 123\n', wg_status='0', host='chill-01', scanner_failed=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            for name, body in {
                'systemctl': '''case "$1" in
list-units) printf '%s' "$FAILED_UNITS"; exit "$SYSTEMD_STATUS" ;;
show)
  case "${2:-}" in
    homelab-download-payloads.timer)
      if [ "${5:-}" = "--value" ]; then echo "$SCANNER_TIMER_LOAD"; else printf 'LastTriggerUSec=n/a\nNextElapseUSecRealtime=n/a\n'; fi ;;
    homelab-download-payloads.service)
      printf 'Result=%s\nExecMainStatus=%s\n' "$SCANNER_RESULT" "$SCANNER_EXIT" ;;
    *) echo not-found ;;
  esac ;;
is-active) [ "${2:-}" = "homelab-download-payloads.timer" ] && [ "$SCANNER_TIMER_ACTIVE" = 1 ] ;;
*) exit 1 ;;
esac
''',
                'wg': '''[ "$*" = 'show wg0 latest-handshakes' ] || exit 99
printf '%s' "$PEERS"
exit "$WG_STATUS"
''',
            }.items():
                p = bin_dir / name
                p.write_text('#!/bin/sh\n' + body)
                p.chmod(0o700)
            output = root / 'metrics'
            env = dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'],
                       HOST_LABEL=host, TEXTFILE_DIR=str(output), FAILED_UNITS=failed,
                       SYSTEMD_STATUS=systemd_status, PEERS=peers, WG_STATUS=wg_status,
                       SCANNER_TIMER_LOAD='loaded' if scanner_failed else 'not-found',
                       SCANNER_TIMER_ACTIVE='1' if scanner_failed else '0',
                       SCANNER_RESULT='exit-code' if scanner_failed else 'success',
                       SCANNER_EXIT='1' if scanner_failed else '0')
            subprocess.run(['sh', str(SCRIPT)], env=env, check=True, capture_output=True)
            self.assertEqual([p.name for p in output.iterdir()], ['homelab.prom'])
            return (output / 'homelab.prom').read_text()

    def test_zero_failed_units_and_peer_labels(self):
        text = self.collect()
        self.assertIn('homelab_systemd_failed_units{host="chill-01"} 0\n', text)
        self.assertIn('homelab_systemd_collect_success{host="chill-01"} 1\n', text)
        self.assertIn('homelab_wireguard_peer_count{host="chill-01",interface="wg0"} 1\n', text)
        self.assertIn('peer="peerbase64="} 123\n', text)

    def test_arbitrary_unit_types_counted(self):
        text = self.collect(failed='broken.service loaded failed failed Example\nbroken.mount loaded failed failed Mount\n')
        self.assertIn('homelab_systemd_failed_units{host="chill-01"} 2\n', text)

    def test_systemd_failure_is_not_zero(self):
        text = self.collect(systemd_status='1')
        self.assertIn('homelab_systemd_collect_success{host="chill-01"} 0\n', text)
        self.assertNotIn('homelab_systemd_failed_units{', text)

    def test_wireguard_failure_has_no_peer_samples(self):
        text = self.collect(wg_status='1')
        self.assertIn('homelab_wireguard_collect_success{host="chill-01",interface="wg0"} 0\n', text)
        self.assertNotIn('homelab_wireguard_peer_count{', text)
        self.assertNotIn('homelab_wireguard_latest_handshake_seconds{', text)

    def test_malformed_runtime_response_is_failure(self):
        text = self.collect(peers='peer 123\ninvalid nope\n')
        self.assertIn('homelab_wireguard_collect_success{host="chill-01",interface="wg0"} 0\n', text)
        self.assertNotIn('homelab_wireguard_latest_handshake_seconds{', text)

    def test_zero_peers_is_successful_empty_collection(self):
        text = self.collect(peers='')
        self.assertIn('homelab_wireguard_peer_count{host="chill-01",interface="wg0"} 0\n', text)
        self.assertIn('homelab_wireguard_collect_success{host="chill-01",interface="wg0"} 1\n', text)

    def test_hypervisor_does_not_collect_wireguard(self):
        text = self.collect(host='malice', wg_status='99')
        self.assertNotIn('homelab_wireguard_collect_success{', text)
        self.assertIn('homelab_metrics_timestamp_seconds{host="malice"}', text)
    def test_download_payload_failure_is_reported_as_a_job_failure(self):
        text = self.collect(scanner_failed=True)
        self.assertIn('homelab_job_failed{host="chill-01",task="download-payloads"} 1\n', text)
        self.assertIn('homelab_job_last_exit_code{host="chill-01",task="download-payloads"} 1\n', text)


if __name__ == '__main__':
    unittest.main()
