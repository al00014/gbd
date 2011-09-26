""" Data models"""

import pylab as pl
import pymc as mc
import scipy.integrate

import data
import rate_model
import age_pattern
import age_integrating_model
import covariate_model
import data_model
import similarity_prior_model
reload(age_pattern)
reload(covariate_model)

def consistent_model(data, hierarchy, node):
    """ Generate PyMC objects for consistent model of epidemological data

    Parameters
    ----------
    data : pandas.DataFrame
      data.columns must include data_type, value, sex, area, age_start, age_end, year_start,
      year_end, effective_sample_size, and each row will be included in the likelihood
    
    Results
    -------
    Returns dict of dicts of PyMC objects, including 'i, p, r, f', the covariate
    adjusted predicted values for each row of data
    """
    ages = pl.arange(101)  # TODO: see if using age mesh and linear interpolation is any faster

    i = data_model.data_model('i', data[data['data_type'] == 'i'], hierarchy, node)
    r = data_model.data_model('r', data[data['data_type'] == 'r'], hierarchy, node)
    f = data_model.data_model('f', data[data['data_type'] == 'f'], hierarchy, node)
    m = .01*pl.ones(101) # TODO: get correct values for m

    logit_C0 = mc.Uninformative('logit_C0', value=-10.)
    p_age_mesh = pl.arange(0,101,2)
    @mc.deterministic
    def mu_age_p(logit_C0=logit_C0, i=i['mu_age'], r=r['mu_age'], f=f['mu_age'], m=m):
        C0 = mc.invlogit(logit_C0)
        SC0 = pl.array([1.-C0, C0])

        def func(SC, a):
            a = int(a)
            if a >= 100:
                return pl.array([0., 0.])
            return pl.array([-(i[a]+m[a])*SC[0] + r[a]*SC[1],
                              i[a]*SC[0] - (r[a]+m[a]+f[a])*SC[1]])

        def Dfun(SC, a):
            a = int(a)
            if a >= 100:
                return pl.array([[0., 0.], [0., 0.]])
            return pl.array([[-(i[a]+m[a]), r[a]],
                             [i[a],  -(r[a]+m[a]+f[a])]])

        SC = scipy.integrate.odeint(func, SC0, p_age_mesh) #, Dfun=Dfun, col_deriv=0)

        #return SC[:,1] / SC.sum(1)
        mu_age_p = scipy.interpolate.interp1d(p_age_mesh, SC[:,1] / SC.sum(1))
        return mu_age_p(ages)
    p = data_model.data_model('p', data[data['data_type'] == 'p'], hierarchy, node, mu_age_p)

    return vars()



def consistent_model_expm(data, hierarchy, node):
    """ Generate PyMC objects for consistent model of epidemological data

    Parameters
    ----------
    data : pandas.DataFrame
      data.columns must include data_type, value, sex, area, age_start, age_end, year_start,
      year_end, effective_sample_size, and each row will be included in the likelihood
    
    Results
    -------
    Returns dict of dicts of PyMC objects, including 'i, p, r, f', the covariate
    adjusted predicted values for each row of data
    """
    ages = pl.arange(101)  # TODO: see if using age mesh and linear interpolation is any faster

    i = data_model.data_model('i', data[data['data_type'] == 'i'], hierarchy, node)
    r = data_model.data_model('r', data[data['data_type'] == 'r'], hierarchy, node)
    f = data_model.data_model('f', data[data['data_type'] == 'f'], hierarchy, node)
    m_all_cause = .01*pl.ones(101) # TODO: get correct values for m

    logit_C0 = mc.Uninformative('logit_C0', value=-10.)
    p_age_mesh = pl.arange(0,101,20)

    # iterative solution to difference equations to obtain bin sizes for all ages
    import scipy.linalg
    @mc.deterministic
    def mu_age_p(logit_C0=logit_C0, i=i['mu_age'], r=r['mu_age'], f=f['mu_age'], m_all_cause=m_all_cause, age_mesh=p_age_mesh):
        SC = pl.zeros([2, len(age_mesh)])
        p = pl.zeros(len(age_mesh))
        m = pl.zeros(len(age_mesh))
        
        SC[0,0] = 1 - mc.invlogit(logit_C0)
        SC[1,0] = 1. - SC[0,0]

        p[0] = SC[0,1] / (SC[0,0] + SC[0,1])
        m[0] = (m_all_cause[age_mesh[0]] - f[age_mesh[0]] * p[0]).clip(
            .1*m_all_cause[age_mesh[0]],
             1-1e-7)  # clip m[0] to avoid numerical instability

        for ii, a in enumerate(age_mesh[:-1]):
            A = pl.array([[-i[a]-m[ii], r[a]           ],
                          [ i[a]     , -r[a]-m[ii]-f[a]]]) * (age_mesh[ii+1] - age_mesh[ii])

            SC[:,ii+1] = pl.dot(scipy.linalg.expm(A), SC[:,ii])
            
            p[ii+1] = (SC[1,ii+1] / (SC[0,ii+1] + SC[1,ii+1])).clip(
                1e-7,
                1-1e-7)
            m[ii+1] = (m_all_cause[age_mesh[ii+1]] - f[age_mesh[ii+1]] * p[ii+1]).clip(
                .1*m_all_cause[age_mesh[ii+1]],
                 pl.inf)
        return scipy.interpolate.interp1d(age_mesh, p, kind='linear')(ages)
    p = data_model.data_model('p', data[data['data_type'] == 'p'], hierarchy, node, mu_age_p)

    return vars()