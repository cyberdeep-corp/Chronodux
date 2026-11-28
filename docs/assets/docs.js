(() => {
 const side=document.getElementById('sidebar'), menu=document.getElementById('menu');
 menu?.addEventListener('click',()=>side.classList.toggle('open'));
 side?.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>side.classList.remove('open')));
 document.querySelectorAll('pre button').forEach(btn=>btn.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(btn.parentElement.querySelector('code').innerText);btn.textContent='Copied'}catch{btn.textContent='Unavailable'}setTimeout(()=>btn.textContent='Copy',1400)}));
 const links=[...document.querySelectorAll('#sidebar a')], sections=links.map(a=>document.querySelector(a.hash)).filter(Boolean);
 if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting)links.forEach(a=>a.classList.toggle('active',a.hash==='#'+e.target.id))}),{rootMargin:'-18% 0px -70% 0px'});sections.forEach(s=>observer.observe(s))}
})();
