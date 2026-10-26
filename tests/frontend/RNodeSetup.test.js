import {expect,it,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import RNodeSetup from '../../meshchatnext/src/frontend/components/setup/RNodeSetup.vue';
it('defaults new RNode connections to Bluetooth LE without writing or changing an existing interface',async()=>{
    window.api={get:vi.fn(),post:vi.fn()};
    const wrapper=mount(RNodeSetup);
    expect(wrapper.findAll('select')[0].element.value).toBe('ble');
    expect(wrapper.findAll('select')[0].findAll('option').map(option=>option.text()).slice(0,2)).toEqual(['Bluetooth LE','Bluetooth Classic']);
    const inputs=wrapper.findAll('input');expect(inputs[1].element.value).toBe('914.875');expect(inputs[2].element.value).toBe('17');
    const selects=wrapper.findAll('select');expect(selects[1].element.value).toBe('125');expect(selects[2].element.value).toBe('8');expect(selects[3].element.value).toBe('7');
    expect(window.api.post).not.toHaveBeenCalled();wrapper.unmount();
});
it('uses ble transport only after an explicit add and preserves an existing matching interface',async()=>{
    window.api={get:vi.fn(async()=>({data:{interfaces:{Existing:{type:'RNodeInterface',port:'ble://AA:BB:CC:DD:EE:FF'}}}})),post:vi.fn()};
    const wrapper=mount(RNodeSetup);
    const inputs=wrapper.findAll('input');await inputs[0].setValue('AA:BB:CC:DD:EE:FF');await inputs[1].setValue('915.000');
    await wrapper.get('form').trigger('submit');await flushPromises();
    expect(wrapper.text()).toContain('already configured');expect(window.api.post).not.toHaveBeenCalled();wrapper.unmount();
});
