// PostgreSQL WASM verifies the same models as SQLite; no BI dashboard is created.
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {PGlite} from '@electric-sql/pglite';
process.on('uncaughtException',error=>{console.error(error.message);process.exit(1);});
const payload=JSON.parse(await fs.readFile('data/postgres_input.json','utf8'));
const pointer=JSON.parse(await fs.readFile('outputs/latest.json','utf8'));
const output=pointer.path;
const db=new PGlite();
await db.exec("SET TIME ZONE 'UTC'");
await db.exec(await fs.readFile('sql/00_schema.sql','utf8'));
await db.query('INSERT INTO settings VALUES ($1)',[payload.as_of]);
for(const [table,rows] of Object.entries(payload.tables)){
  const columns=Object.keys(rows[0]);
  for(let offset=0;offset<rows.length;offset+=300){
    const batch=rows.slice(offset,offset+300);
    const placeholders=batch.map((_,i)=>'('+columns.map((_,j)=>'$'+(i*columns.length+j+1)).join(',')+')');
    await db.query(`INSERT INTO ${table} (${columns.map(c=>'"'+c+'"').join(',')}) VALUES ${placeholders.join(',')}`,
      batch.flatMap(row=>columns.map(c=>row[c])));
  }
}
for(const name of ['10_delivery_models.sql','20_billing_models.sql'])await db.exec(await fs.readFile('sql/'+name,'utf8'));
const source=(await fs.readFile('sql/30_analytical_queries.sql','utf8')).split('\n').filter(l=>!l.trimStart().startsWith('--')).join('\n');
const analyses=await db.exec(source);
assert.equal(analyses.length,8);
const actual=(await db.query('SELECT commitment_id,delivered,original_delivered,expected_billable_cents,net_invoiced_cents,billing_difference_cents FROM v_commitment_finance ORDER BY commitment_id')).rows;
const expected=new Map(payload.expected_fact.map(r=>[r.commitment_id,r]));
assert.equal(actual.length,expected.size);
for(const row of actual)for(const field of ['delivered','original_delivered','expected_billable_cents','net_invoiced_cents','billing_difference_cents']){
  assert.equal(Number(row[field]),Number(expected.get(row.commitment_id)[field]),row.commitment_id+' '+field);
}
await db.exec(await fs.readFile('sql/40_reporting_security.sql','utf8'));
await db.exec(`INSERT INTO tv_reporting.commitment_summary
 SELECT commitment_id,advertiser_id,campaign_id,due_commitment,delivered,expected_billable_cents,net_invoiced_cents
 FROM v_commitment_finance`);
for(const id of [1,2]){
  await db.exec(`SET ROLE advertiser_${id}`);
  assert.deepEqual((await db.query('SELECT DISTINCT advertiser_id FROM tv_reporting.commitment_summary')).rows.map(r=>r.advertiser_id),[id]);
  for(const sql of ['SELECT * FROM public.invoice_lines LIMIT 1','DELETE FROM tv_reporting.commitment_summary']){
    let denied=false;try{await db.query(sql);}catch{denied=true;}assert(denied);
  }
  await db.exec('RESET ROLE');
}
const checks={engine:(await db.query('SELECT version() AS v')).rows[0].v,
  environment:'PGlite PostgreSQL WASM, single process; not production server performance',
  analytical_queries_executed:8,commitments_compared:actual.length,sqlite_postgres_parity:'MATCH',
  advertiser_isolation:'PASS for two NOLOGIN roles',raw_invoice_access:'DENIED',report_writes:'DENIED'};
await fs.writeFile(output+'/reports/postgres_verification.json',JSON.stringify(checks,null,2)+'\n');

// Isolated fixture: leave application indexes intact. Compare the same query.
await db.exec('CREATE TABLE benchmark_commitments AS SELECT * FROM commitments; ANALYZE benchmark_commitments;');
const query=`SELECT COUNT(*) AS n FROM benchmark_commitments WHERE booking_line_id='B0001-0'
 AND due_at >= TIMESTAMPTZ '2026-01-01T00:00:00Z' AND due_at < TIMESTAMPTZ '2026-07-01T00:00:00Z'`;
const beforeResult=(await db.query(query)).rows;
async function plans(){
  await db.query(query);await db.query(query);
  const out=[];for(let i=0;i<7;i++)out.push((await db.query('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+query)).rows[0]['QUERY PLAN'][0]);
  return out;
}
const before=await plans();
await db.exec('CREATE INDEX benchmark_booking_due ON benchmark_commitments(booking_line_id,due_at); ANALYZE benchmark_commitments;');
const after=await plans();assert.deepEqual((await db.query(query)).rows,beforeResult);
const median=values=>[...values].sort((a,b)=>a-b)[Math.floor(values.length/2)];
const benchmark={environment:checks.environment,engine:checks.engine,rows:actual.length,query,
  warmups:2,repeats:7,results_equal:true,before_median_ms:median(before.map(p=>p['Execution Time'])),
  after_median_ms:median(after.map(p=>p['Execution Time'])),before_plans:before,after_plans:after};
await fs.writeFile(output+'/reports/query_benchmark.json',JSON.stringify(benchmark,null,2)+'\n');
console.log(JSON.stringify({...checks,before_ms:benchmark.before_median_ms,after_ms:benchmark.after_median_ms},null,2));
await db.close();
