const els={};const el=id=>els[id]||(els[id]={value:'',textContent:''});
global.document={getElementById:el};
let remoto, escritos=[], confirmaRespuesta=true, falla=false, selecc=[];
async function leerDatosExtraRemotos(){ if(falla) throw new Error('sin red'); return JSON.parse(JSON.stringify(remoto)); }
async function guardarEnDrive(o){ escritos.push(o); }
global.confirm=()=>confirmaRespuesta;
function seleccionarProyectoExtra(id){ selecc.push(id); }
function rfRefrescarExtra(){}
let datosExtra={}, proyectoSeleccionado={id_proyecto:'P1'}, usuarioActualEmail='yo@x.cl';
const assert=(c,m)=>{ if(!c){ console.log('FALLA:',m); process.exit(1);} };
(async()=>{
  // Caso 1: sin conflicto; otro proyecto P2 cambió en Drive -> se conserva
  remoto={P1:{profesional:'A',evento:'E'},P2:{observaciones:'nuevo de otra persona'}};
  snapshotExtra=JSON.stringify(remoto.P1); el('f-profesional').value='B'; el('f-evento').value='E';
  await guardarDatosExtra();
  assert(escritos.length===1,'debe escribir 1 vez');
  assert(escritos[0].P2.observaciones==='nuevo de otra persona','conserva P2 de otra persona');
  assert(escritos[0].P1.profesional==='B','guarda el cambio');
  assert(escritos[0].P1.historial_cambios.length===1 && escritos[0].P1.historial_cambios[0].antes.profesional==='A','historial con valor anterior');
  assert(escritos[0].P1.ultima_edicion_por==='yo@x.cl','autor');
  // Caso 2: conflicto y usuario cancela -> no escribe
  remoto={P1:{profesional:'Z',ultima_edicion_por:'otro@x.cl'}}; snapshotExtra=JSON.stringify({profesional:'A'});
  confirmaRespuesta=false; await guardarDatosExtra();
  assert(escritos.length===1,'no debe escribir si cancela'); assert(selecc[0]==='P1','recarga el formulario');
  // Caso 3: conflicto y usuario acepta -> escribe
  confirmaRespuesta=true; await guardarDatosExtra();
  assert(escritos.length===2,'escribe si acepta');
  // Caso 4: falla la lectura -> no escribe nada
  falla=true; await guardarDatosExtra();
  assert(escritos.length===2,'no escribe si no puede leer'); assert(el('save-status').textContent.includes('no se cambió nada'),'mensaje de error');
  console.log('OK: 4 casos');
})();
