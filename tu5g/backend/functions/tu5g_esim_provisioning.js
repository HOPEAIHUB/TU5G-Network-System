/**
 * TU5G E-SIM Provisioning Service
 * Generates SIM numbers in the +984799000000 to +984799999999 range
 * Provisions virtual e-SIMs with QR code activation data
 */

const COUNTRY_CODE = '+984';
const SIM_PREFIX = '799';
const SIM_RANGE_START = 799000000;
const SIM_RANGE_END = 799999999;
const HMAIL_DOMAIN = 'tu5g.online';

export async function handleRequest(req, res) {
  const body = await req.json();
  const base44 = createClientFromRequest(req);
  
  const { action } = body;
  
  try {
    if (action === 'list_numbers') {
      const { category, page = 1, perPage = 20 } = body;
      const pageNum = parseInt(page);
      const perPageNum = parseInt(perPage);
      
      // Generate available numbers
      const numbers = [];
      const start = (pageNum - 1) * perPageNum;
      
      for (let i = 0; i < perPageNum; i++) {
        const suffix = String(SIM_RANGE_START + start + i);
        const phoneNumber = `${COUNTRY_CODE}${suffix}`;
        const price = category === 'vanity' ? 500 : category === 'premium' ? 100 : 0;
        
        numbers.push({
          number: phoneNumber,
          category: category || 'free',
          price,
          available: true,
        });
      }
      
      return Response.json({
        success: true,
        numbers,
        page: pageNum,
        perPage: perPageNum,
        total: 1000000, // Full range
      });
    }
    
    if (action === 'provision') {
      const { userId, number, planType, numberCategory } = body;
      
      // Generate ICCID (20-digit)
      const iccid = `89${COUNTRY_CODE.slice(1)}${String(Math.floor(Math.random() * 1e15)).padStart(15, '0')}`;
      
      // Generate QR code activation data (LPA format)
      const qrData = `LPA:1:tugs.tu5g.online:${iccid}`;
      
      // Set plan details
      const plans = {
        free_3months: { allowance: 5, duration: 3, price: 0 },
        premium: { allowance: 10, duration: 1, price: 9.99 },
        ultra: { allowance: 999, duration: 1, price: 29.99 },
        business: { allowance: 100, duration: 1, price: 49.99 },
      };
      
      const plan = plans[planType] || plans.free_3months;
      const expiresDate = new Date();
      expiresDate.setMonth(expiresDate.getMonth() + (planType === 'free_3months' ? 3 : 1));
      
      // Create e-SIM record
      const esim = await base44.entities.ESim.create({
        userId,
        phoneNumber: number,
        countryCode: COUNTRY_CODE,
        iccid,
        numberCategory: numberCategory || 'free',
        planType,
        status: 'active',
        planExpires: expiresDate.toISOString(),
        dataAllowanceGb: plan.allowance,
        dataUsedGb: 0,
        qrCodeData: qrData,
      });
      
      // Create HMAIL account if KYC verified
      const users = await base44.entities.TU5GUser.list({ filter: { id: userId }, limit: 1 });
      if (users && users.length > 0 && users[0].kycStatus === 'verified') {
        const username = number.replace('+', '');
        await base44.entities.HmailAccount.create({
          userId,
          accountId: userId,
          username,
          address: `${username}@${HMAIL_DOMAIN}`,
          isActive: true,
        });
      }
      
      return Response.json({
        success: true,
        message: 'E-SIM provisioned successfully',
        esim: {
          id: esim.id,
          phoneNumber: number,
          iccid,
          planType,
          status: 'active',
          planExpires: expiresDate.toISOString(),
          dataAllowanceGb: plan.allowance,
          qrCodeData: qrData,
        },
      });
    }
    
    if (action === 'get_status') {
      const { esimId } = body;
      const esims = await base44.entities.ESim.list({ filter: { id: esimId }, limit: 1 });
      
      if (!esims || esims.length === 0) {
        return Response.json({ success: false, message: 'E-SIM not found' }, { status: 404 });
      }
      
      return Response.json({ success: true, esim: esims[0] });
    }
    
    if (action === 'get_plans') {
      return Response.json({
        success: true,
        plans: [
          { id: 'free_3months', name: 'Free Plan', duration: '3 months', dataGb: 5, price: 0, description: '3 months free, 5GB per month' },
          { id: 'premium', name: 'Premium Plan', duration: '1 month', dataGb: 10, price: 9.99, description: '10GB per month' },
          { id: 'ultra', name: 'Ultra Plan', duration: '1 month', dataGb: 999, price: 29.99, description: 'Unlimited data' },
          { id: 'business', name: 'Business Plan', duration: '1 month', dataGb: 100, price: 49.99, description: '100GB per month' },
        ],
      });
    }
    
    if (action === 'suspend') {
      const { esimId } = body;
      await base44.entities.ESim.update(esimId, { status: 'suspended' });
      return Response.json({ success: true, message: 'E-SIM suspended' });
    }
    
    if (action === 'activate') {
      const { esimId } = body;
      await base44.entities.ESim.update(esimId, { status: 'active' });
      return Response.json({ success: true, message: 'E-SIM activated' });
    }
    
    if (action === 'check_number_price') {
      const { number, category } = body;
      const prices = { free: 0, premium: 100, vanity: 500 };
      return Response.json({
        success: true,
        number,
        category: category || 'free',
        price: prices[category] || 0,
      });
    }
    
    return Response.json({ success: false, message: 'Unknown action' }, { status: 400 });
  } catch (err) {
    console.error('E-SIM service error:', err);
    return Response.json({ success: false, message: 'Internal server error', error: err.message }, { status: 500 });
  }
}
