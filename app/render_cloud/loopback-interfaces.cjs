// Expose the network interfaces available to this worker's asset servers.
// The syscall broker enforces the actual network policy.
const os = require('node:os');
const {syncBuiltinESMExports} = require('node:module');
os.networkInterfaces = () => ({
  lo: [
    {address:'127.0.0.1',netmask:'255.0.0.0',family:'IPv4',mac:'00:00:00:00:00:00',internal:true,cidr:'127.0.0.1/8'},
  ],
});
syncBuiltinESMExports();
