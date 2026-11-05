/* Complete managed image models share the existing picker, drafts and reviews. */
window.ManagedImageBundles = (() => {
  const slots=[byId('store-image-bundles'),byId('settings-image-bundles')];
  const kinds=['comfy-install','comfy-import','comfy-remove','comfy-recover','comfy-repair','comfy-store-install'];
  let data=null,reading=false,again=false,busy=false,epoch=0,timer=null,error='',receipt=null;
  const visible=()=>authenticated&&latest?.image_comfyui&&
    (currentView==='store'||currentView==='settings'&&settingsSection==='models');
  const name=id=>data?.items?.find(item=>item.id===id)?.name||(id==='sd15-control@1'?'Stable Diffusion 1.5':id);
  async function choose(model=data?.bundle.id){
    const auth=authEpoch;
    try{
      showView('settings',{section:'models'});ModelsSettingsNavigation.show('image',{focus:true});
      await BrowserMedia.whenLoaded();
      if(!authenticated||auth!==authEpoch||!data||currentView!=='settings'||settingsSection!=='models')return;
      if(SettingsDrafts.category('image-service').drafts.changed().length)throw new Error('Apply or discard your image settings draft before choosing this model.');
      byId('image-service-provider').value='comfyui';
      byId('image-service-provider').dispatchEvent(new Event('change'));
      byId('image-service-model-name').value=model;byId('image-service-enabled').checked=true;
      byId('image-service-model-name').dispatchEvent(new Event('input',{bubbles:true}));
      byId('image-service-model-name-picker').focus();
    }catch(e){error=e.message;render();}
  }
  function showInventory(){StoreDesign.openImages('installed');}
  async function review(draft={operation:'comfy-install'}){
    if(busy)return;busy=true;error='';render();const auth=authEpoch;
    try{
      await prepareChange(draft,{
        current:()=>authenticated&&auth===authEpoch,
        onAccepted:result=>{if(auth!==authEpoch)return;receipt=result;busy=false;
          if(['comfy-import','comfy-store-install'].includes(draft.operation))showInventory();refresh();loadOperations();},
        onDiscard:()=>{if(auth!==authEpoch)return;busy=false;refresh();},
      });
    }catch(e){if(auth===authEpoch){busy=false;error=e.message;render();
      const target=byId('store-detail-blocker');if(target&&!byId('store-detail').hidden)target.textContent=e.message;}}
  }
  async function check(model){
    if(busy)return;busy=true;error='Verifying checkpoint…';render();const auth=authEpoch;
    try{const result=await domainRequest('/api/v1/settings/models/image-bundles','POST',{action:'check',model});
      if(auth===authEpoch)error=`${new Date(result.checked_at*1000).toLocaleString()}: ${result.message}`;
    }catch(e){if(auth===authEpoch)error=e.message;}
    finally{if(auth===authEpoch){busy=false;render();}}
  }
  async function pause(){
    if(busy||!data?.pending)return;busy=true;error='';render();const auth=authEpoch;
    try{await domainRequest('/api/v1/settings/models/image-bundle-pause','POST',{request_id:data.pending.request_id});}
    catch(e){if(auth===authEpoch)error=e.message;}
    finally{if(auth===authEpoch){busy=false;refresh();}}
  }
  function managedEmpty(node,title,description=''){const box=domainText('div','','managed-empty');collectionEmpty(box,title,description,'image');box.setAttribute('role','status');node.append(box);}
  function render(){
    const params=new URLSearchParams(location.search),section=params.get('models-section')||'discover';
    const runtime=byId('store-runtime').value,images=runtime==='comfyui';
    for(const [index,node] of slots.entries()){
      node.hidden=!visible()||index===0&&(byId('store-panel').hidden||window.IntegrationStoreUI?.isOpen()||
        !images&&runtime!=='all'||runtime==='all'&&section==='downloads'&&!data?.pending);
      if(index===1)node.hidden=node.hidden||!data?.pending&&(Boolean(data?.items?.some(item=>item.installed))||Boolean(byId('image-service-model-name').value));
      if(node.hidden)continue;
      const opened=new Set([...node.querySelectorAll('details[open][data-managed-model]')].map(n=>n.dataset.managedModel));
      const focused=node.contains(document.activeElement)?document.activeElement.dataset.managedAction:'';
      node.replaceChildren();
      if(index===1){
        if(!data?.pending)node.append(domainText('p',error||'No image models installed.','muted'));
      }else if(section!=='downloads'){
        const heading=domainText('div','','store-section-heading');heading.append(domainText('h2',section==='installed'?'Installed image models':'Image models'));
        if(!images)heading.append(domainButton('See all',()=>StoreDesign.openImages(),'quiet'));
        node.append(heading);
      }
      if(!data){if(index===0)node.append(domainText('p',error||'Loading image models…','muted'));continue;}
      if(index===0&&images)for(const [section,total] of [['installed',data.items?.filter(item=>item.installed).length||0],['downloads',data.pending?1:0]]){const tab=byId('store-tab-'+section);let badge=tab.querySelector('.tab-count');if(!badge){badge=domainText('span','','tab-count');tab.prepend(badge);}badge.textContent=total;}
      if(data.pending){
        const progress=receipt?.request_id===data.pending.request_id&&receipt.progress?.stage?receipt.progress:data.pending.progress;
        const text=data.pending.checking?'Checking saved state…':data.pending.state==='unknown'?
          (data.pending.kind==='comfy-remove'?'Removal unconfirmed':'Installation paused or unconfirmed'):
          progress?.stage||(data.pending.kind==='comfy-remove'?'Removing model…':'Preparing image model…');
        const panel=domainText('div','','managed-install-progress');
        const status=domainText('p',text);status.setAttribute('role','status');panel.append(status);
        const actions=domainText('div','','dialog-actions');
        const button=domainButton(data.pending.state==='unknown'?(data.pending.kind==='comfy-remove'?'Check removal':'Check installation'):'Pause',()=>data.pending.state==='unknown'?
          review({operation:'comfy-recover',target:data.pending.request_id}):pause(),'secondary');
        button.dataset.managedAction='pending';button.disabled=busy||data.pending.checking||data.pending.state==='cancelling';
        if(data.pending.kind!=='comfy-remove'||data.pending.state==='unknown')actions.append(button);
        const meter=document.createElement('progress');meter.setAttribute('aria-label','Image model installation');
        if(progress?.total>0){meter.max=progress.total;meter.value=progress.completed||0;}
        panel.append(meter,actions);node.append(panel);
      }
      if(index===1){if(error){const status=domainText('p',error);status.setAttribute('role','status');node.append(status);}continue;}
      if(section==='downloads'){
        if(!data.pending)managedEmpty(node,'No active image downloads','','image');
        if(error){const status=domainText('p',error);status.setAttribute('role','status');node.append(status);}continue;
      }
      const items=[{id:data.bundle.id,name:data.bundle.name,size:data.bundle.size,installed:data.installed,generation_verified:data.generation_verified,architecture:'sd-1.5'},
        ...(data.items||[]).filter(item=>item.id!==data.bundle.id)];
      const query=byId('store-query').value.trim().toLocaleLowerCase();
      const matches=items.filter(item=>(section!=='installed'||item.installed)&&`${item.name} ${item.architecture}`.toLocaleLowerCase().includes(query));
      const list=domainText('div','','managed-image-list');
      for(const item of matches){
        const row=domainText('article','','managed-image-row');row.dataset.managedModel=item.id;
        const icon=domainText('span','','managed-image-icon');icon.append(libraryIcon('image'));
        const text=domainText('div','','store-card-content');
        text.append(domainText('strong',item.name),domainText('small',item.installed?'Installed':'Complete image model','muted'));
        if(!item.installed&&item.size)text.append(domainText('small',fileSize(item.size),'muted'));
        const actions=domainText('div','','managed-image-controls');
        const button=(label,fn,style='secondary')=>{const b=domainButton(label,fn,style);b.disabled=busy||Boolean(data.pending)||!data.bundle.install_available;b.dataset.managedAction=item.id+':'+label;actions.append(b);return b;};
        if(item.installed)button('Use model',()=>choose(item.id)).dataset.bundleChoose='true';
        else if(item.id===data.bundle.id)button(data.setup_started?'Continue install':'Install',()=>review()).dataset.bundleInstall='true';
        else if(item.source_model)button('Repair',()=>review({operation:'comfy-repair',model:item.id}));
        const details=domainText('details','','managed-image-actions');details.dataset.managedModel=item.id;details.open=opened.has(item.id);
        details.append(domainText('summary',item.installed?'Manage':'Details'));
        if(item.installed){
          details.append(domainButton('Check files',()=>check(item.id),'quiet'),
            domainButton('Repair installation',()=>review(item.id===data.bundle.id?{operation:'comfy-install'}:{operation:'comfy-repair',model:item.id}),'quiet'),
            domainButton('Remove model',()=>review({operation:'comfy-remove',model:item.id}),'quiet danger'));
          details.append(domainText('p',item.generation_verified?'Previous generation succeeded':'Generation not yet tested','muted'));
        }
        const source=domainText('a','Source and license');source.href=item.source_url||data.bundle.source_url;source.target='_blank';source.rel='noopener noreferrer';details.append(source);
        if(item.id===data.bundle.id&&item.installed)details.querySelectorAll('button')[1].dataset.bundleInstall='true';
        details.querySelectorAll('button').forEach((b,i)=>{b.disabled=busy||Boolean(data.pending);b.dataset.managedAction=item.id+':manage:'+i;});
        row.append(icon,text,actions,details);list.append(row);
        if(item.message){const message=domainText('p',item.message,'managed-image-message');message.setAttribute('role','status');row.append(message);}
      }
      node.append(list);
      if(!matches.length)managedEmpty(node,query?'No matching image models':'No image models installed',section==='installed'?'Find a model in Discover.':'','image');
      if(section==='discover'){
        const details=domainText('details','','catalog-disclosure');details.append(domainText('summary','Installation details'));
        const facts=domainText('dl','','preview-metadata');
        for(const [label,value] of [['Runtime','ComfyUI '+(data.runtime_version||'0.43.0')],['First setup','Allow 12 GiB of disk space'],['Supported imports','Complete SD1.5 and SDXL safetensors checkpoints']])facts.append(domainText('dt',label),domainText('dd',value));
        details.append(facts);node.append(details);
      }
      if(data.support_message)node.append(domainText('p',data.support_message,'muted'));
      if(error){const message=domainText('p',error);message.setAttribute('role','status');node.append(message);}
      if(focused)[...node.querySelectorAll('[data-managed-action]')].find(n=>n.dataset.managedAction===focused)?.focus({preventScroll:true});
    }
  }
  async function refresh(){
    render();if(!visible())return;if(reading){again=true;return;}reading=true;const auth=authEpoch,id=++epoch;
    try{
      const result=await domainRequest('/api/v1/settings/models/image-bundles','POST',{action:'list'});
      if(auth!==authEpoch||id!==epoch)return;data=result;
      clearInterval(timer);timer=null;
      if(data.pending&&(data.pending.state!=='unknown'||data.pending.checking)||receipt&&['accepted','running','cancelling'].includes(receipt.state))timer=setInterval(()=>{refresh();loadOperations();},2000);
    }catch(e){if(auth===authEpoch&&id===epoch)error=e.message;}
    finally{if(auth===authEpoch&&id===epoch){reading=false;render();if(again){again=false;refresh();}}}
  }
  document.addEventListener('klaude-view',refresh);
  document.addEventListener('klaude-snapshot',()=>{if(visible()&&!data)refresh();});
  document.addEventListener('klaude-operations',event=>{const item=event.detail.find(item=>kinds.includes(item.kind));
    if(item){const changed=receipt?.request_id!==item.request_id||receipt?.state!==item.state;receipt=item;render();if(changed)refresh();}});
  document.addEventListener('klaude-auth-reset',()=>{epoch++;data=receipt=null;reading=again=busy=false;error='';clearInterval(timer);timer=null;slots.forEach(node=>{node.hidden=true;node.replaceChildren();});});
  return {render,refresh,choose,name,install:(model,downloaded=true)=>{const item=data?.items?.find(item=>item.installed&&item.source_model===model);return item?choose(item.id):review({operation:downloaded?'comfy-import':'comfy-store-install',model});}};
})();
