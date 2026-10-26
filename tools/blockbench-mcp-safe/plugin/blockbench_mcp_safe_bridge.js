/* Optional, explicit opt-in, read-only live snapshots from Blockbench desktop.
 * Never reads MCP requests or executes them. Never opens a network port.
 * UI must manually connect the workspace. Source code can be inspected locally.
 */
let mcpSafeAction, mcpSafeTimer=null;
Plugin.register('blockbench_mcp_safe_bridge',{
  title:'Blockbench MCP Safe Bridge (Read Only)',author:'Blockbench MCP Safe contributors',
  version:'0.4.0',variant:'desktop',min_version:'5.0.0',icon:'security',
  description:'Optional local read-only bridge. User explicitly selects the MCP workspace; publishes bounded status, scene and preview snapshots.',
  onload(){
    mcpSafeAction=new Action('bbms_bridge_connect',{name:'Connect Read-Only MCP Safe Bridge',icon:'visibility',
      click:()=>{
        if(mcpSafeTimer){clearInterval(mcpSafeTimer);mcpSafeTimer=null;Blockbench.showQuickMessage('MCP bridge disconnected');return;}
        const root=window.prompt('Enter the ABSOLUTE MCP Safe --root workspace directory (read-only snapshots, no remote commands):');
        if(!root)return;
        try{
          if(typeof require!=='function')throw Error('Desktop filesystem API is unavailable');
          const fs=require('fs'),path=require('path'),crypto=require('crypto');
          const resolved=fs.realpathSync(root);
          if(!path.isAbsolute(root)||!fs.statSync(resolved).isDirectory())throw Error('Choose an existing absolute directory');
          const bridge=path.join(resolved,'.bbms-live');
          if(!fs.existsSync(bridge))fs.mkdirSync(bridge,{mode:0o700});
          if(!fs.lstatSync(bridge).isDirectory()||fs.realpathSync(bridge)!==bridge)throw Error('Unsafe bridge directory');
          const atomic=(file,buf)=>{
            if(buf.length>768*1024)throw Error('Bridge snapshot exceeds 768 KiB');
            const temp=path.join(bridge,'.bbms-'+crypto.randomBytes(8).toString('hex')+'.tmp');
            fs.writeFileSync(temp,buf,{flag:'wx',mode:0o600});
            try{
              const target=path.join(bridge,file);
              if(fs.existsSync(target)&&(!fs.lstatSync(target).isFile()||fs.lstatSync(target).nlink!==1))throw Error('Unsafe snapshot target');
              fs.renameSync(temp,target);
            }finally{if(fs.existsSync(temp))fs.unlinkSync(temp);}
          };
          const publish=()=>{
            let screenshotAt=null;
            const now=Date.now();
            const project=typeof Project!=='undefined'&&Project?Project:null;
            const cubes=typeof Cube!=='undefined'?Cube.all.slice(0,250).map(c=>({uuid:c.uuid,name:c.name,from:[...c.from],to:[...c.to],origin:[...c.origin]})):[];
            const bones=typeof Group!=='undefined'?Group.all.slice(0,250).map(g=>({uuid:g.uuid,name:g.name,origin:[...g.origin],rotation:[...g.rotation]})):[];
            const scene={timestamp:now,name:project?.name||null,cubes,bones,truncated:(typeof Cube!=='undefined'&&Cube.all.length>250)||(typeof Group!=='undefined'&&Group.all.length>250)};
            atomic('scene.json',Buffer.from(JSON.stringify(scene)));
            // WebGL preview capture is best-effort. It may be empty on some GPU/drivers.
            try{
              const canvas=typeof Preview!=='undefined'?Preview.selected?.canvas:null;
              const url=canvas?.toDataURL?.('image/png');
              if(typeof url==='string'&&url.startsWith('data:image/png;base64,')){
                const png=Buffer.from(url.slice(22),'base64');if(png.length>100&&png.length<=768*1024){atomic('preview.png',png);screenshotAt=now;}
              }
            }catch{} // Snapshot remains optional; status still works.
            atomic('status.json',Buffer.from(JSON.stringify({timestamp:now,connected:true,project:project?.name||null,model_format:project?.format?.id||null,cubes:cubes.length,bones:bones.length,mode:'read-only snapshots',screenshot:'best effort',screenshot_at:screenshotAt})));
          };
          publish();mcpSafeTimer=setInterval(()=>{try{publish();}catch(e){console.warn('[MCP Safe Bridge]',e.message);}},2000);
          Blockbench.showQuickMessage('MCP Safe read-only bridge connected (click again to disconnect)');
        }catch(e){Blockbench.showMessageBox({title:'MCP Safe Bridge',message:String(e.message||e)});}
      }
    });
    MenuBar.menus.tools.addAction(mcpSafeAction);
  },
  onunload(){if(mcpSafeTimer){clearInterval(mcpSafeTimer);mcpSafeTimer=null;}mcpSafeAction?.delete();}
});
