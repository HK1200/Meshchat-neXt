import {beforeEach,expect,it,vi} from 'vitest';
import {setupSteps,configureReticulumSetup,applySetupRadio2,RMAP_TCP} from '../../meshchatnext/src/frontend/js/firstLaunchSetup';
import {meshcoreBackupChoices,isBluetoothAddress} from '../../meshchatnext/src/frontend/js/meshcoreSetupBackup';
function apiFor(interfaces={}){
    const rows=structuredClone(interfaces);
    return {get:vi.fn(async()=>({data:{interfaces:rows}})),patch:vi.fn(async()=>({data:{}})),post:vi.fn(async(path,body)=>{
        if(path.endsWith('/interfaces/add'))rows[body.name]={...body};
        return {data:path.endsWith('/receive-announces')?{changed:[],reload_required:false}:{}};
    })};
}
it.each(Array.from({length:8},(_,bits)=>[bits]))('builds only relevant setup steps for feature combination %s',bits=>{
    const features={reticulum:!!(bits&1),meshcore:!!(bits&2),sip:!!(bits&4)};
    const steps=setupSteps(features);
    expect(steps[0]).toBe('networks');expect(steps.at(-1)).toBe('ready');
    expect(steps.includes('identity')).toBe(features.reticulum);
    expect(steps.includes('meshcore')).toBe(features.meshcore);
    expect(steps.includes('radio2')).toBe(features.meshcore);
    expect(steps.includes('sip')).toBe(features.sip);
});
it('configures the requested RMAP TCP exactly once across retries, without bootstrap-only suppression',async()=>{
    const api=apiFor();const options={internet:true,local:false,...RMAP_TCP};
    await configureReticulumSetup(api,options);await configureReticulumSetup(api,options);
    const adds=api.post.mock.calls.filter(([path])=>path.endsWith('/interfaces/add'));
    expect(adds).toHaveLength(1);expect(adds[0][1]).toMatchObject({target_host:'rmap.world',target_port:4242,bootstrap_only:false});
    expect(api.patch.mock.calls.find(([path])=>path.endsWith('/config'))[1]).toMatchObject({announce_store_lxmf_delivery:true,announce_store_lxst_telephony:true});
});
it('keeps existing interfaces and never adds internet without opt in',async()=>{
    const api=apiFor({Radio:{type:'RNodeInterface',port:'ble://fixture'},LAN:{type:'AutoInterface'}});
    await configureReticulumSetup(api,{internet:false,local:true});
    expect(api.post.mock.calls.some(([path])=>path.endsWith('/interfaces/add'))).toBe(false);
    expect(api.post.mock.calls.some(([path])=>path.endsWith('/receive-announces'))).toBe(true);
});
it('reuses and enables an existing RMAP entry without overwriting its secrets',async()=>{
    const api=apiFor({Private:{type:'TCPClientInterface',target_host:'rmap.world',target_port:'4242',enabled:'False',passphrase:'fixture'}});
    await configureReticulumSetup(api,{internet:true,local:false,...RMAP_TCP});
    expect(api.post).toHaveBeenCalledWith('/api/v1/reticulum/interfaces/enable',{name:'Private'});
    expect(api.post.mock.calls.some(([path])=>path.endsWith('/interfaces/add'))).toBe(false);
});
it('validates TCP before making any changes',async()=>{
    const api=apiFor();await expect(configureReticulumSetup(api,{internet:true,host:'bad\nhost',port:4242})).rejects.toThrow();
    expect(api.get).not.toHaveBeenCalled();expect(api.post).not.toHaveBeenCalled();
});
it('does not probe or change Radio2 when keeping existing firmware',async()=>{
    const api=apiFor();expect(await applySetupRadio2(api,'keep',null)).toEqual({unchanged:true});expect(api.get).not.toHaveBeenCalled();
});
it('keeps standard messaging available on unsupported firmware and refuses media writes',async()=>{
    const api={get:vi.fn(async()=>({data:{result:{supported:false}}})),post:vi.fn()};
    expect(await applySetupRadio2(api,'standard','owner')).toMatchObject({enabled:false});
    await expect(applySetupRadio2(api,'media','owner')).rejects.toThrow('does not support Radio2');expect(api.post).not.toHaveBeenCalled();
});
it('applies only the chosen Radio2 profile and requires verified isolated media routing',async()=>{
    const profile={frequency_mhz:911.15,bandwidth_khz:250,sf:7,cr:5};
    const api={get:vi.fn(async()=>({data:{result:{supported:true,enabled:false,defaults:profile}}})),post:vi.fn(async()=>({data:{result:{supported:true,enabled:true,crossing:false,media_policy:'radio2'}}}))};
    await applySetupRadio2(api,'media','owner','us915');
    expect(api.post).toHaveBeenCalledWith('/api/v1/meshcore/radio2',{enabled:true,...profile,expected_owner:'owner'});
    api.post.mockResolvedValue({data:{result:{supported:true,enabled:true,crossing:true,media_policy:'both'}}});
    await expect(applySetupRadio2(api,'media','owner','us915')).rejects.toThrow('not verified');
});
it('does not substitute a US profile when the user chose their existing Radio2 profile',async()=>{
    const api={get:vi.fn(async()=>({data:{result:{supported:true,profile:null,defaults:{frequency_mhz:911.15}}}})),post:vi.fn()};
    await expect(applySetupRadio2(api,'media','owner','keep')).rejects.toThrow('local group');expect(api.post).not.toHaveBeenCalled();
});
it('selects per-device backup configurations without mixing identities and validates Bluetooth hints',()=>{
    const value={devices:[{name:'One',bluetooth_address:'aa:bb:cc:dd:ee:ff',config:{private_key:'fixture-one',channels:[]}},{name:'Two',bluetooth_address:'not an address',config:{contacts:[],private_key:'fixture-two'}}]};
    const rows=meshcoreBackupChoices(value);
    expect(rows).toHaveLength(2);expect(rows[0].connection).toEqual({kind:'ble',target:'AA:BB:CC:DD:EE:FF'});
    expect(rows[1].connection).toBeNull();expect(rows[0].config.private_key).toBe('fixture-one');expect(rows[1].config.private_key).toBe('fixture-two');
    expect(isBluetoothAddress('a'.repeat(64))).toBe(false);
    expect(()=>meshcoreBackupChoices({devices:new Array(33).fill({})})).toThrow();
    expect(()=>meshcoreBackupChoices({devices:[{unrecognized:true}]})).toThrow('not supported');
});
